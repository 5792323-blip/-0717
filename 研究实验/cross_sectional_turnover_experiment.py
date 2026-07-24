#!/usr/bin/env python3
"""20日反转的换手缓冲、分批轮换与分散持仓训练。"""

import argparse
import json
import math
import os
from datetime import datetime

from 研究实验.cross_sectional_baseline_experiment import 评价, 精简
from 运行程序.run_backtest import 读取股票列表
from 组合回测.横截面组合 import 加载面板, 读取交易成本, 运行组合


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
候选方案 = [
    {"名称": "Top5_基线", "top_k": 5, "retain_rank": None, "max_replacements": None, "rebalance_every": 5},
    {"名称": "Top5_保留Top10", "top_k": 5, "retain_rank": 10, "max_replacements": None, "rebalance_every": 5},
    {"名称": "Top5_保留Top15", "top_k": 5, "retain_rank": 15, "max_replacements": None, "rebalance_every": 5},
    {"名称": "Top5_保留Top10_每次换1只", "top_k": 5, "retain_rank": 10, "max_replacements": 1, "rebalance_every": 5},
    {"名称": "Top5_保留Top15_每次换1只", "top_k": 5, "retain_rank": 15, "max_replacements": 1, "rebalance_every": 5},
    {"名称": "Top8_保留Top16", "top_k": 8, "retain_rank": 16, "max_replacements": None, "rebalance_every": 5},
    {"名称": "Top10_保留Top20", "top_k": 10, "retain_rank": 20, "max_replacements": None, "rebalance_every": 5},
    {"名称": "Top5_每10日", "top_k": 5, "retain_rank": None, "max_replacements": None, "rebalance_every": 10},
    {"名称": "Top5_每15日", "top_k": 5, "retain_rank": None, "max_replacements": None, "rebalance_every": 15},
    {"名称": "Top8_无缓冲", "top_k": 8, "retain_rank": None, "max_replacements": None, "rebalance_every": 5},
    {"名称": "Top10_无缓冲", "top_k": 10, "retain_rank": None, "max_replacements": None, "rebalance_every": 5},
    {"名称": "Top15_无缓冲", "top_k": 15, "retain_rank": None, "max_replacements": None, "rebalance_every": 5},
]


def main():
    parser = argparse.ArgumentParser(description="20日反转换手与分散训练")
    parser.add_argument("--stocks", default="数据模块/hs300_list.txt")
    parser.add_argument("--config", default="1_策略配置")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--capital", type=float, default=20_000_000)
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    if args.end >= "2024-01-01":
        raise ValueError("换手优化训练结束日期必须早于封存验证期2024-01-01")

    output_dir = args.output_dir or os.path.join(
        项目根目录, "10_实验记录",
        f"横截面换手与分散训练_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )
    os.makedirs(output_dir, exist_ok=True)
    stocks = 读取股票列表(args.stocks)
    daily = 加载面板(stocks, args.start, args.end)
    available = [stock for stock in stocks if stock in daily]
    buckets = [[stock for index, stock in enumerate(available) if index % 3 == bucket] for bucket in range(3)]
    costs = 读取交易成本(os.path.abspath(args.config))
    report = {
        "训练期": [args.start, args.end], "封存验证期": "未读取", "可用股票数": len(available),
        "固定设置": {"因子": "20日反转", "调仓频率": "每5个交易日", "目标总仓位": 0.8},
        "候选": {},
    }
    for candidate in 候选方案:
        name = candidate["名称"]
        kwargs = {
            "top_k": candidate["top_k"], "retain_rank": candidate["retain_rank"],
            "max_replacements": candidate["max_replacements"],
            "rebalance_every": candidate["rebalance_every"],
        }
        full = 运行组合(
            daily, available, "20日反转", args.start, args.end, costs,
            args.capital, **kwargs,
        )
        bucket_top_k = max(3, math.ceil(candidate["top_k"] / 3))
        bucket_retain_rank = (
            None if candidate["retain_rank"] is None
            else max(bucket_top_k, math.ceil(candidate["retain_rank"] / 3))
        )
        bucket_results = [
            运行组合(
                daily, bucket, "20日反转", args.start, args.end, costs, args.capital,
                top_k=bucket_top_k, retain_rank=bucket_retain_rank,
                max_replacements=candidate["max_replacements"],
                rebalance_every=candidate["rebalance_every"],
            ) for bucket in buckets
        ]
        full["权益曲线"].to_csv(os.path.join(output_dir, f"{name}_权益曲线.csv"), encoding="utf-8-sig")
        full["交易明细"].to_csv(os.path.join(output_dir, f"{name}_交易明细.csv"), index=False, encoding="utf-8-sig")
        report["候选"][name] = {
            "参数": candidate, "全池": 精简(full),
            "股票桶": [精简(result) for result in bucket_results],
            "评价": 评价(full, bucket_results),
        }

    ranked = sorted(report["候选"], key=lambda name: (
        int(report["候选"][name]["评价"]["合格"]),
        report["候选"][name]["评价"]["正收益年度数"],
        report["候选"][name]["评价"]["正收益分桶年度数"],
        report["候选"][name]["评价"]["横截面得分"],
    ), reverse=True)
    report["排名"] = ranked
    report["合格候选"] = [name for name in ranked if report["候选"][name]["评价"]["合格"]]
    with open(os.path.join(output_dir, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(report, target, ensure_ascii=False, indent=2)
    with open(os.path.join(output_dir, "中文报告.md"), "w", encoding="utf-8") as target:
        target.write("# 20日反转换手缓冲与分散训练\n\n")
        target.write("- 仅使用2020-2023训练期；封存验证未读取。\n")
        target.write("- 固定20日反转、80%仓位和成本模型；对比调仓频率、排名缓冲和持仓数。\n\n")
        target.write("|排名|方案|合格|总收益|最大回撤|正收益年度|正收益分桶|最差年度|双边换手|\n")
        target.write("|---:|---|---|---:|---:|---:|---:|---:|---:|\n")
        for index, name in enumerate(ranked, 1):
            full = report["候选"][name]["全池"]
            evaluation = report["候选"][name]["评价"]
            qualified = "是" if evaluation["合格"] else "否"
            target.write(
                f"|{index}|{name}|{qualified}|{full['总收益率']:.2%}|{full['最大回撤']:.2%}|"
                f"{evaluation['正收益年度数']}/4|{evaluation['正收益分桶年度数']}/12|"
                f"{evaluation['最差年度收益']:.2%}|{full['累计双边换手']:.1f}x|\n"
            )
    print(json.dumps({"输出目录": output_dir, "排名": ranked, "合格候选": report["合格候选"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
