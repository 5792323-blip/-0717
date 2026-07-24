#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在独立股票信号之上重放共享资金池，验证组合风险控制。"""

import argparse
import contextlib
import io
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime

import pandas as pd
import yaml

项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 项目根目录)

from 回测引擎.backtest_engine import 跑回测
from 数据模块.股票加载器 import 加载股票


方案 = {
    "原始仓位": {"仓位倍数": 1.0, "单股上限": 1.0, "总暴露上限": 1.0, "现金底线": 0.0},
    "2倍风险预算": {"仓位倍数": 2.0, "单股上限": 0.10, "总暴露上限": 0.80, "现金底线": 0.20},
    "3倍风险预算": {"仓位倍数": 3.0, "单股上限": 0.10, "总暴露上限": 0.80, "现金底线": 0.20},
    "4倍风险预算": {"仓位倍数": 4.0, "单股上限": 0.10, "总暴露上限": 0.80, "现金底线": 0.20},
}


def 数值(value, default=0.0):
    try:
        value = float(value)
        return value if pd.notna(value) else default
    except (TypeError, ValueError):
        return default


def 读取股票列表(path):
    with open(path, encoding="utf-8") as source:
        stocks = [item.strip().replace("SH_", "").replace("SZ_", "") for item in source if item.strip()]
    return list(dict.fromkeys(stocks))


def 读取交易成本(config_dir):
    path = os.path.join(config_dir, "参数配置.yaml")
    with open(path, encoding="utf-8") as source:
        config = yaml.safe_load(source)
    costs = config.get("交易成本", {})
    return {
        "佣金": float(costs.get("佣金", 0.00025)),
        "印花税": float(costs.get("印花税", 0.001)),
        "过户费": float(costs.get("过户费", 0.00001)),
    }


def 提取交易(result, stock):
    records = []
    for _, row in result["交易明细"].iterrows():
        timestamp = pd.Timestamp(row.get("时间"))
        trade_type = row.get("类型")
        if trade_type == "买入":
            price = 数值(row.get("买入价"))
            shares = int(数值(row.get("成交数量")))
            if price > 0 and shares >= 100:
                records.append({
                    "时间": timestamp,
                    "类型": "买入",
                    "股票代码": stock,
                    "价格": price,
                    "股数": shares,
                    "信号类型": row.get("信号类型", ""),
                })
        elif trade_type == "卖出":
            price = 数值(row.get("卖出价"))
            if price > 0:
                records.append({
                    "时间": timestamp,
                    "类型": "卖出",
                    "股票代码": stock,
                    "价格": price,
                    "股数": 0,
                    "信号类型": row.get("卖出原因", ""),
                })
    return records


def _运行单股信号(task):
    stock, config, start, end, capital, liquidity_limit = task
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result = 跑回测(
                stock,
                开始日期=start,
                结束日期=end,
                初始资金=capital,
                配置目录=config,
                运行参数={"流动性上限比例": liquidity_limit},
                静默=True,
            )
        if result is None:
            return stock, [], None, "无可用回测结果"
        data = result["原始K线数据"].copy()
        data["时间"] = pd.to_datetime(data["日期"])
        price = data[["时间", "不复权_收盘"]].dropna().set_index("时间")["不复权_收盘"]
        return stock, 提取交易(result, stock), price, None
    except Exception as error:
        return stock, [], None, str(error)


def 运行独立信号(stocks, config, start, end, capital, liquidity_limit, workers=1):
    trades = []
    prices = {}
    errors = []
    tasks = [(stock, config, start, end, capital, liquidity_limit) for stock in stocks]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            results = executor.map(_运行单股信号, tasks)
            results = list(results)
    else:
        results = [_运行单股信号(task) for task in tasks]
    for stock, stock_trades, price, error in results:
        trades.extend(stock_trades)
        if price is not None:
            prices[stock] = price
        if error:
            errors.append({"股票代码": stock, "错误": error})
    return (
        sorted(trades, key=lambda item: (item["时间"], item["股票代码"], item["类型"])),
        prices,
        errors,
    )


def 价格截至(series, timestamp):
    if series is None:
        return 0.0
    values = series.loc[:timestamp]
    return 数值(values.iloc[-1]) if len(values) else 0.0


def 重放组合(trades, prices, capital, limits, costs):
    cash = float(capital)
    holdings = {}
    equity_points = []
    accepted_buys = 0
    rejected_buys = 0
    sells = 0
    wins = 0
    realized_pnl = []

    def equity(timestamp):
        market_value = sum(
            item["股数"] * 价格截至(prices.get(stock), timestamp)
            for stock, item in holdings.items()
        )
        return cash + market_value, market_value

    events = {}
    for trade in trades:
        events.setdefault(trade["时间"], []).append(trade)
    timeline = sorted(set(events).union(
        timestamp for series in prices.values() for timestamp in series.index
    ))

    for timestamp in timeline:
        # 同一时点先卖后买，使现金释放顺序固定且可复现。
        current_events = sorted(
            events.get(timestamp, []),
            key=lambda item: (0 if item["类型"] == "卖出" else 1, item["股票代码"]),
        )
        for trade in current_events:
            total_equity, market_value = equity(timestamp)
            stock = trade["股票代码"]
            if trade["类型"] == "买入":
                if stock in holdings:
                    rejected_buys += 1
                    continue
                if len(holdings) >= int(limits.get("最大持仓数", 10**9)):
                    rejected_buys += 1
                    continue
                target = min(
                    trade["股数"] * trade["价格"] * limits.get("仓位倍数", 1.0),
                    total_equity * limits["单股上限"],
                    total_equity * limits["总暴露上限"] - market_value,
                    cash - total_equity * limits["现金底线"],
                )
                shares = int(max(0.0, target) / trade["价格"] / 100) * 100
                trade_value = shares * trade["价格"]
                commission = max(trade_value * costs["佣金"], 5) if shares else 0
                transfer_fee = trade_value * costs["过户费"] if shares else 0
                total_cost = trade_value + commission + transfer_fee
                if shares >= 100 and total_cost <= cash:
                    cash -= total_cost
                    holdings[stock] = {
                        "股数": shares,
                        "成本": trade["价格"],
                        "总成本": total_cost,
                    }
                    accepted_buys += 1
                else:
                    rejected_buys += 1
            else:
                if stock not in holdings:
                    continue
                position = holdings.pop(stock)
                proceeds = position["股数"] * trade["价格"]
                commission = max(proceeds * costs["佣金"], 5)
                transfer_fee = proceeds * costs["过户费"]
                tax = proceeds * costs["印花税"]
                net = proceeds - commission - transfer_fee - tax
                pnl = net - position["总成本"]
                cash += net
                sells += 1
                wins += int(pnl > 0)
                realized_pnl.append(pnl)

        total_equity, market_value = equity(timestamp)
        equity_points.append({"时间": timestamp.isoformat(), "现金": cash, "持仓市值": market_value, "权益": total_equity})

    last_time = max((series.index.max() for series in prices.values()), default=pd.Timestamp.now())
    final_equity, market_value = equity(last_time)
    curve = pd.Series([item["权益"] for item in equity_points] or [capital])
    drawdown = float(((curve.cummax() - curve) / curve.cummax()).max())
    total_return = final_equity / capital - 1
    if timeline:
        years = max((timeline[-1] - timeline[0]).days / 365.25, 1 / 252)
    else:
        years = 1 / 252
    annual_return = (1 + total_return) ** (1 / years) - 1 if total_return > -1 else -1
    gross_profit = sum(value for value in realized_pnl if value > 0)
    gross_loss = -sum(value for value in realized_pnl if value < 0)
    return {
        "初始资金": capital,
        "最终权益": final_equity,
        "总收益率": total_return,
        "年化收益率": annual_return,
        "最大回撤": drawdown,
        "收益回撤比": annual_return / max(drawdown, 1e-9),
        "Profit Factor": gross_profit / gross_loss if gross_loss else 0.0,
        "买入成交": accepted_buys,
        "买入拦截": rejected_buys,
        "卖出成交": sells,
        "胜率": wins / sells if sells else 0.0,
        "最终持仓数": len(holdings),
        "权益曲线": equity_points,
    }


def main():
    parser = argparse.ArgumentParser(description="组合级共享资金池风险控制实验")
    parser.add_argument("--stocks", default="数据模块/hs300_prescreen_30.txt")
    parser.add_argument("--config", default="1_策略配置")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--capital", type=float, default=20_000_000)
    parser.add_argument("--liquidity-limit", type=float, default=0.01)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--max-positions", type=int, default=200)
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    stocks = 读取股票列表(args.stocks)
    config_dir = os.path.abspath(args.config)
    costs = 读取交易成本(config_dir)
    trades, prices, errors = 运行独立信号(
        stocks, config_dir, args.start, args.end, args.capital, args.liquidity_limit, args.workers
    )
    output_dir = args.output_dir or os.path.join(项目根目录, "10_实验记录", f"组合风险控制训练实验_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(output_dir, exist_ok=True)
    report = {"训练期": [args.start, args.end], "股票数": len(prices), "股票列表": stocks,
              "最大持仓数": args.max_positions, "错误": errors, "交易成本": costs, "方案": {}}
    for name, limits in 方案.items():
        current_limits = {**limits, "最大持仓数": args.max_positions}
        report["方案"][name] = 重放组合(trades, prices, args.capital, current_limits, costs)
        curve = report["方案"][name].pop("权益曲线")
        pd.DataFrame(curve).to_csv(os.path.join(output_dir, f"{name}_权益曲线.csv"), index=False, encoding="utf-8-sig")
    with open(os.path.join(output_dir, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(report, target, ensure_ascii=False, indent=2)
    with open(os.path.join(output_dir, "报告.md"), "w", encoding="utf-8") as target:
        target.write("# 组合风险控制训练期实验\n\n")
        target.write(f"- 训练期：{args.start} 至 {args.end}\n- 股票数：{len(prices)}\n- 验证期：未读取\n\n")
        target.write("|方案|收益率|年化收益|最大回撤|收益回撤比|PF|买入成交|卖出成交|胜率|\n|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for name, result in report["方案"].items():
            target.write(
                f"|{name}|{result['总收益率']:.2%}|{result['年化收益率']:.2%}|"
                f"{result['最大回撤']:.2%}|{result['收益回撤比']:.3f}|"
                f"{result['Profit Factor']:.3f}|{result['买入成交']}|"
                f"{result['卖出成交']}|{result['胜率']:.2%}|\n"
            )
    print(json.dumps({"实验目录": output_dir, "方案": report["方案"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
