#!/usr/bin/env python3
"""分析沪深300亏损交易的共同入场与退出特征。"""

import argparse
import contextlib
import io
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime

import numpy as np
import pandas as pd


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 项目根目录)

from 回测引擎.backtest_engine import 跑回测


def 读取股票(value):
    if os.path.isfile(value):
        with open(value, encoding="utf-8") as source:
            values = [line.strip() for line in source if line.strip()]
    else:
        values = [item.strip() for item in value.split(",") if item.strip()]
    return [item.replace("SH_", "").replace("SZ_", "") for item in values]


def 前序日成交额比率(data):
    dates = data["日期"].astype(str).str[:10]
    daily = data.groupby(dates)["成交额"].sum().sort_index()
    previous_mean = daily.shift(1).rolling(20, min_periods=5).mean()
    ratio = daily / previous_mean
    return ratio.to_dict()


def 单股分析(task):
    stock, config_dir, start, end = task
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result = 跑回测(
                stock,
                开始日期=start,
                结束日期=end,
                初始资金=20_000_000,
                配置目录=config_dir,
                运行参数={"流动性上限比例": 0.01},
                静默=True,
            )
        if result is None:
            return {"股票代码": stock, "错误": "无回测结果"}
        data = result["原始K线数据"].copy()
        time_map = {str(index)[:19]: position for position, index in enumerate(data.index)}
        amount_ratio = 前序日成交额比率(data) if "成交额" in data.columns else {}
        buys = result["交易明细"]
        buys = buys[(buys["类型"] == "买入") & pd.to_numeric(buys["盈亏比例"], errors="coerce").notna()]
        records = []
        for _, trade in buys.iterrows():
            timestamp = str(trade.get("时间", ""))[:19]
            position = time_map.get(timestamp)
            if position is None:
                continue
            row = data.iloc[position]
            rsi = float(row.get("RSI_14")) if pd.notna(row.get("RSI_14")) else None
            ma = float(row.get("RSI_均线_20")) if pd.notna(row.get("RSI_均线_20")) else None
            ma_slope = None
            if position >= 5 and ma is not None:
                previous_ma = data.iloc[position - 5].get("RSI_均线_20")
                if pd.notna(previous_ma):
                    ma_slope = (ma - float(previous_ma)) / 5
            trade_date = str(row.get("日期", ""))[:10]
            records.append({
                "股票代码": stock,
                "时间": timestamp,
                "信号类型": trade.get("信号类型"),
                "盈亏比例": float(trade.get("盈亏比例")),
                "持有K线数": float(trade.get("持有K线数")) if pd.notna(trade.get("持有K线数")) else None,
                "卖出原因": trade.get("卖出原因"),
                "入场RSI": rsi,
                "入场RSI_MA": ma,
                "入场MA斜率5": ma_slope,
                "当日成交额比20日均值": amount_ratio.get(trade_date),
            })
        return {"股票代码": stock, "交易": records}
    except Exception as error:
        return {"股票代码": stock, "错误": str(error)}


def 比例(frame, condition):
    return float(condition.mean()) if len(frame) else 0.0


def 汇总(records):
    frame = pd.DataFrame(records)
    losses = frame[frame["盈亏比例"] < 0].copy()
    wins = frame[frame["盈亏比例"] > 0].copy()
    scenarios = []
    if len(losses):
        scenarios = [
            {
                "场景": "高MA斜率追涨后亏损",
                "亏损交易占比": 比例(losses, losses["入场MA斜率5"] > 2),
                "盈利交易占比": 比例(wins, wins["入场MA斜率5"] > 2),
            },
            {
                "场景": "RSI低于30抄底后亏损",
                "亏损交易占比": 比例(losses, losses["入场RSI"] < 30),
                "盈利交易占比": 比例(wins, wins["入场RSI"] < 30),
            },
            {
                "场景": "成交额低于20日均值70%时入场",
                "亏损交易占比": 比例(losses, losses["当日成交额比20日均值"] < 0.7),
                "盈利交易占比": 比例(wins, wins["当日成交额比20日均值"] < 0.7),
            },
        ]
    exit_counts = losses["卖出原因"].fillna("未知").value_counts().head(10).to_dict()
    signal_stats = []
    for signal, group in frame.groupby("信号类型", dropna=False):
        signal_stats.append({
            "信号类型": str(signal),
            "交易数": int(len(group)),
            "胜率": float((group["盈亏比例"] > 0).mean()),
            "平均盈亏": float(group["盈亏比例"].mean()),
        })
    return {
        "总交易数": int(len(frame)),
        "亏损交易数": int(len(losses)),
        "盈利交易数": int(len(wins)),
        "整体胜率": float((frame["盈亏比例"] > 0).mean()) if len(frame) else 0.0,
        "三大场景": scenarios,
        "亏损退出原因Top10": exit_counts,
        "信号统计": signal_stats,
        "亏损交易明细": losses.to_dict(orient="records"),
    }


def 写报告(path, summary, start, end, errors):
    scenarios = sorted(summary["三大场景"], key=lambda item: item["亏损交易占比"], reverse=True)
    lines = [
        "# 当前策略在沪深300上的三大失效场景",
        "",
        "## 数据范围",
        "",
        f"- 实际诊断区间：{start} 至 {end}。",
        "- 本地行情最早从2020-01-02开始，缺少2015-2019数据，无法完成2015-2023完整训练诊断。",
        f"- 成功股票数：{300 - errors}；失败/数据不足：{errors}。",
        f"- 已闭合交易：{summary['总交易数']}；整体胜率：{summary['整体胜率']:.2%}。",
        "",
        "## 三大失效场景",
        "",
    ]
    for index, item in enumerate(scenarios[:3], 1):
        difference = item["亏损交易占比"] - item["盈利交易占比"]
        lines.append(
            f"{index}. {item['场景']}：亏损交易占比 {item['亏损交易占比']:.2%}，"
            f"盈利交易占比 {item['盈利交易占比']:.2%}，差异 {difference:+.2%}。"
        )
    lines.extend(["", "## 信号归因", ""])
    for item in sorted(summary["信号统计"], key=lambda row: row["平均盈亏"]):
        lines.append(
            f"- {item['信号类型']}：{item['交易数']}笔，胜率 {item['胜率']:.2%}，"
            f"平均盈亏 {item['平均盈亏']:.2%}。"
        )
    lines.extend(["", "## 亏损退出原因", ""])
    for reason, count in summary["亏损退出原因Top10"].items():
        lines.append(f"- {reason}：{count}笔。")
    with open(path, "w", encoding="utf-8") as target:
        target.write("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description="沪深300亏损交易归因")
    parser.add_argument("--stocks", default="数据模块/hs300_list.txt")
    parser.add_argument("--config", default="1_策略配置")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.abspath(args.output_dir) if args.output_dir else os.path.join(
        项目根目录, "10_实验记录", f"亏损归因_{timestamp}"
    )
    os.makedirs(output_dir, exist_ok=True)
    stocks = 读取股票(args.stocks)
    tasks = [(stock, os.path.abspath(args.config), args.start, args.end) for stock in stocks]
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        results = list(executor.map(单股分析, tasks))
    records = [trade for result in results for trade in result.get("交易", [])]
    summary = 汇总(records)
    errors = sum("错误" in result for result in results)
    with open(os.path.join(output_dir, "亏损归因.json"), "w", encoding="utf-8") as target:
        json.dump(summary, target, ensure_ascii=False, indent=2, default=str)
    pd.DataFrame(records).to_csv(
        os.path.join(output_dir, "全部闭合交易.csv"), index=False, encoding="utf-8-sig"
    )
    写报告(os.path.join(output_dir, "当前策略在沪深300上的三大失效场景.md"), summary, args.start, args.end, errors)
    print(json.dumps({"输出目录": output_dir, "汇总": {key: value for key, value in summary.items() if key != "亏损交易明细"}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
