#!/usr/bin/env python3
"""训练期逐笔MFE/MAE诊断，为退出结构设计提供依据。"""

import argparse
import contextlib
import io
import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime

import pandas as pd


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 项目根目录)

from 回测引擎.backtest_engine import 跑回测
from 运行程序.run_backtest import 读取股票列表


def 数值(value, default=None):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def 配对交易(details):
    rows = details.sort_values("时间").to_dict("records")
    pairs = []
    pending = None
    for row in rows:
        if row.get("类型") == "买入":
            pending = row
        elif row.get("类型") == "卖出" and pending is not None:
            pairs.append((pending, row))
            pending = None
    return pairs


def 提取逐笔(result, stock):
    raw = result["原始K线数据"].copy()
    raw.index = pd.to_datetime(raw.index)
    raw = raw.sort_index()
    records = []
    for buy, sell in 配对交易(result["交易明细"]):
        entry_time = pd.Timestamp(buy["时间"])
        exit_time = pd.Timestamp(sell["时间"])
        entry = 数值(buy.get("买入价"))
        realized = 数值(sell.get("盈亏比例"))
        window = raw.loc[entry_time:exit_time]
        if not entry or realized is None or window.empty:
            continue
        high_returns = window["不复权_最高"].astype(float) / entry - 1
        low_returns = window["不复权_最低"].astype(float) / entry - 1
        close_returns = window["不复权_收盘"].astype(float) / entry - 1
        record = {
            "股票代码": stock,
            "买入时间": entry_time.isoformat(),
            "卖出时间": exit_time.isoformat(),
            "信号类型": buy.get("信号类型", ""),
            "实现收益": realized,
            "MFE": float(high_returns.max()),
            "MAE": float(low_returns.min()),
            "利润回吐": float(high_returns.max() - realized),
            "持有K线数": len(window),
            "MFE出现K线": int(high_returns.values.argmax()) + 1,
            "MAE出现K线": int(low_returns.values.argmin()) + 1,
        }
        for bars in (4, 8, 12):
            position = min(bars, len(window)) - 1
            prefix = window.iloc[: position + 1]
            record[f"第{bars}根收盘收益"] = float(close_returns.iloc[position])
            record[f"前{bars}根MFE"] = float(prefix["不复权_最高"].astype(float).max() / entry - 1)
            record[f"前{bars}根MAE"] = float(prefix["不复权_最低"].astype(float).min() / entry - 1)
            record[f"实际持有达到{bars}根"] = len(window) >= bars
        records.append(record)
    return records


def 执行任务(task):
    stock, config, start, end, capital, liquidity_limit = task
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result = 跑回测(
                stock, start, end, capital,
                配置目录=config,
                运行参数={"流动性上限比例": liquidity_limit},
                静默=True,
            )
        return {"股票代码": stock, "交易": 提取逐笔(result, stock)}
    except Exception as error:
        return {"股票代码": stock, "错误": str(error), "交易": []}


def 中位数(frame, column):
    return float(frame[column].median()) if len(frame) else 0.0


def profit_factor(values):
    gains = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    return gains / losses if losses else 0.0


def 汇总(frame):
    wins = frame[frame["实现收益"] > 0]
    losses = frame[frame["实现收益"] <= 0]
    summary = {
        "交易数": len(frame),
        "胜率": len(wins) / len(frame) if len(frame) else 0.0,
        "平均实现收益": float(frame["实现收益"].mean()) if len(frame) else 0.0,
        "Profit Factor": profit_factor(frame["实现收益"].tolist()),
        "盈利交易MFE中位数": 中位数(wins, "MFE"),
        "亏损交易MFE中位数": 中位数(losses, "MFE"),
        "盈利交易MAE中位数": 中位数(wins, "MAE"),
        "亏损交易MAE中位数": 中位数(losses, "MAE"),
        "盈利交易利润回吐中位数": 中位数(wins, "利润回吐"),
        "亏损交易中MFE不足0.5%占比": float((losses["MFE"] < 0.005).mean()) if len(losses) else 0.0,
    }
    time_stop = {}
    for bars in (4, 8, 12):
        eligible = (
            frame[f"实际持有达到{bars}根"]
            & (frame[f"前{bars}根MFE"] < 0.005)
            & (frame[f"第{bars}根收盘收益"] < 0)
        )
        simulated = frame["实现收益"].copy()
        simulated.loc[eligible] = frame.loc[eligible, f"第{bars}根收盘收益"]
        time_stop[f"{bars}根无效交易退出"] = {
            "触发交易数": int(eligible.sum()),
            "替换后平均收益_未计额外成本": float(simulated.mean()),
            "替换后ProfitFactor_未计额外成本": profit_factor(simulated.tolist()),
            "相对原始平均收益变化": float(simulated.mean() - frame["实现收益"].mean()),
        }
    summary["时间退出近似模拟"] = time_stop
    return summary


def main():
    parser = argparse.ArgumentParser(description="训练期MFE/MAE诊断")
    parser.add_argument("--stocks", default="数据模块/hs300_prescreen_30.txt")
    parser.add_argument("--config", required=True)
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--capital", type=float, default=20_000_000)
    parser.add_argument("--liquidity-limit", type=float, default=0.01)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    stocks = 读取股票列表(args.stocks)
    config = os.path.abspath(args.config)
    tasks = [(stock, config, args.start, args.end, args.capital, args.liquidity_limit) for stock in stocks]
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            results = list(executor.map(执行任务, tasks))
    else:
        results = [执行任务(task) for task in tasks]
    records = [trade for result in results for trade in result["交易"]]
    frame = pd.DataFrame(records)
    if frame.empty:
        raise RuntimeError("没有可诊断的闭合交易")

    output_dir = args.output_dir or os.path.join(
        项目根目录, "10_实验记录", f"MFE_MAE训练诊断_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )
    os.makedirs(output_dir, exist_ok=True)
    frame.to_csv(os.path.join(output_dir, "逐笔MFE_MAE.csv"), index=False, encoding="utf-8-sig")
    payload = {
        "训练期": [args.start, args.end],
        "验证期": "未读取",
        "股票池": args.stocks,
        "配置目录": config,
        "失败股票": [result for result in results if "错误" in result],
        "汇总": 汇总(frame),
    }
    with open(os.path.join(output_dir, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False, indent=2)
    with open(os.path.join(output_dir, "中文报告.md"), "w", encoding="utf-8") as target:
        s = payload["汇总"]
        target.write("# MFE/MAE训练期诊断\n\n")
        target.write(f"- 训练期：{args.start} 至 {args.end}\n- 验证期：未读取\n- 闭合交易：{s['交易数']}\n\n")
        target.write(
            f"- 胜率：{s['胜率']:.2%}；平均实现收益：{s['平均实现收益']:.3%}；PF：{s['Profit Factor']:.3f}\n"
            f"- 盈利交易MFE中位数：{s['盈利交易MFE中位数']:.2%}；亏损交易MFE中位数：{s['亏损交易MFE中位数']:.2%}\n"
            f"- 盈利交易MAE中位数：{s['盈利交易MAE中位数']:.2%}；亏损交易MAE中位数：{s['亏损交易MAE中位数']:.2%}\n"
            f"- 盈利交易利润回吐中位数：{s['盈利交易利润回吐中位数']:.2%}\n"
            f"- 亏损交易中MFE不足0.5%占比：{s['亏损交易中MFE不足0.5%占比']:.2%}\n\n"
        )
        target.write("## 时间退出近似模拟\n\n")
        target.write("仅作诊断，使用第N根收盘收益替换原结果，未加入额外滑点和费用。\n\n")
        target.write("|方案|触发交易|平均收益变化|替换后PF|\n|---|---:|---:|---:|\n")
        for name, result in s["时间退出近似模拟"].items():
            target.write(
                f"|{name}|{result['触发交易数']}|{result['相对原始平均收益变化']:+.3%}|"
                f"{result['替换后ProfitFactor_未计额外成本']:.3f}|\n"
            )
    print(json.dumps({"输出目录": output_dir, "汇总": payload["汇总"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
