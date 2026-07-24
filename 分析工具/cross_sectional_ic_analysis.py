#!/usr/bin/env python3
"""训练期横截面IC诊断：信号日收盘计算因子，次日开盘进入，未来5日收益。"""

import argparse
import json
import math
import os
from datetime import datetime

import numpy as np
import pandas as pd

from 运行程序.run_backtest import 读取股票列表
from 组合回测.横截面组合 import 因子列表, 加载面板


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def 构建面板(daily_by_stock):
    frames = []
    for stock, daily in daily_by_stock.items():
        frame = daily[["momentum_20", "reversal_5", "low_volatility_20", "liquidity_20"]].copy()
        # 信号在t日收盘形成，t+1开盘进入，t+5收盘退出。
        frame["forward_5"] = daily["close"].shift(-5) / daily["open"].shift(-1) - 1
        frame["stock"] = stock
        frames.append(frame.reset_index().rename(columns={"交易日": "date", "index": "date"}))
    panel = pd.concat(frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])
    return panel.replace([np.inf, -np.inf], np.nan)


def 因子分数(group, factor):
    def rank(column):
        return group[column].rank(pct=True)
    momentum = rank("momentum_20")
    reversal = rank("reversal_5")
    low_volatility = rank("low_volatility_20")
    liquidity = rank("liquidity_20")
    if factor == "20日动量":
        return momentum
    if factor == "20日反转":
        return 1.0 - momentum
    if factor == "5日反转":
        return reversal
    if factor == "低波动":
        return low_volatility
    if factor == "成交活跃":
        return liquidity
    if factor == "动量质量复合":
        return 0.5 * momentum + 0.3 * low_volatility + 0.2 * liquidity
    if factor == "反转质量复合":
        return 0.5 * reversal + 0.3 * low_volatility + 0.2 * liquidity
    raise ValueError(factor)


def 计算日期截面(group, factor, minimum_assets=20):
    data = group.copy()
    data["score"] = 因子分数(data, factor)
    data = data[["score", "forward_5"]].dropna()
    if len(data) < minimum_assets:
        return None
    ic = data["score"].corr(data["forward_5"], method="spearman")
    percentile = data["score"].rank(pct=True)
    top = data.loc[percentile > 0.8, "forward_5"].mean()
    bottom = data.loc[percentile <= 0.2, "forward_5"].mean()
    return {
        "样本数": len(data), "IC": float(ic),
        "高分组收益": float(top), "低分组收益": float(bottom),
        "多空收益差": float(top - bottom),
    }


def 汇总(records):
    frame = pd.DataFrame(records)
    result = {}
    for year, rows in frame.groupby(frame["date"].dt.year):
        ic_std = rows["IC"].std(ddof=0)
        result[str(year)] = {
            "交易日数": len(rows),
            "平均IC": float(rows["IC"].mean()),
            "IC正值比例": float((rows["IC"] > 0).mean()),
            "IC_IR": float(rows["IC"].mean() / ic_std) if ic_std > 0 else 0.0,
            "平均高分组收益": float(rows["高分组收益"].mean()),
            "平均低分组收益": float(rows["低分组收益"].mean()),
            "平均多空收益差": float(rows["多空收益差"].mean()),
        }
    return result


def main():
    parser = argparse.ArgumentParser(description="横截面因子IC训练诊断")
    parser.add_argument("--stocks", default="数据模块/hs300_list.txt")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    if args.end >= "2024-01-01":
        raise ValueError("IC训练结束日期必须早于封存验证期")
    output_dir = args.output_dir or os.path.join(
        项目根目录, "10_实验记录",
        f"横截面IC训练诊断_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )
    os.makedirs(output_dir, exist_ok=True)
    stocks = 读取股票列表(args.stocks)
    daily = 加载面板(stocks, args.start, args.end)
    panel = 构建面板(daily)
    panel = panel[(panel["date"] >= args.start) & (panel["date"] <= args.end)]
    report = {
        "训练期": [args.start, args.end], "封存验证期": "未读取",
        "股票数": len(daily), "未来收益": "t+1开盘至t+5收盘", "因子": {},
    }
    for factor in 因子列表:
        records = []
        for date, group in panel.groupby("date"):
            item = 计算日期截面(group, factor)
            if item is not None and math.isfinite(item["IC"]):
                records.append({"date": date, **item})
        yearly = 汇总(records)
        signs = [np.sign(item["平均IC"]) for item in yearly.values() if item["平均IC"] != 0]
        report["因子"][factor] = {
            "年度": yearly,
            "正IC年度数": sum(item["平均IC"] > 0 for item in yearly.values()),
            "负IC年度数": sum(item["平均IC"] < 0 for item in yearly.values()),
            "方向一致": len(set(signs)) <= 1,
            "四年平均IC": float(np.mean([item["平均IC"] for item in yearly.values()])),
            "四年平均多空收益差": float(np.mean([item["平均多空收益差"] for item in yearly.values()])),
        }
    with open(os.path.join(output_dir, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(report, target, ensure_ascii=False, indent=2)
    with open(os.path.join(output_dir, "中文报告.md"), "w", encoding="utf-8") as target:
        target.write("# 横截面因子IC训练诊断\n\n")
        target.write(f"- 训练期：{args.start}至{args.end}；封存验证未读取。\n")
        target.write(f"- 股票数：{len(daily)}；未来收益：t+1开盘至t+5收盘。\n\n")
        target.write("|因子|四年平均IC|正IC年度|负IC年度|方向一致|平均多空收益差|\n")
        target.write("|---|---:|---:|---:|---|---:|\n")
        for factor, result in report["因子"].items():
            target.write(
                f"|{factor}|{result['四年平均IC']:.4f}|{result['正IC年度数']}/4|"
                f"{result['负IC年度数']}/4|{'是' if result['方向一致'] else '否'}|"
                f"{result['四年平均多空收益差']:.3%}|\n"
            )
        target.write("\n只有方向跨年度一致、且多空收益差为正的因子才可以进入下一轮组合回测。\n")
    print(json.dumps({"输出目录": output_dir, "因子": report["因子"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
