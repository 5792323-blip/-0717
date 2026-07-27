#!/usr/bin/env python3
"""网格风控参数敏感性实验；只修改实验副本，不修改正式配置。"""

import argparse
import json
import os
from datetime import datetime

from 研究实验.exit_rule_experiment import 复制配置
from 研究实验.grid_risk_limits_experiment import 回测, 设置网格风控


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def 解析方案(text):
    """解析 名称:间隔:冻结K线，名称中不允许使用冒号。"""
    plans = []
    for item in text.split(","):
        name, interval, freeze_bars = item.split(":")
        plans.append((name, int(interval), int(freeze_bars)))
    return plans


def 差异(candidate, baseline):
    return {
        key: candidate[key] - baseline[key]
        for key in baseline.keys() & candidate.keys()
        if isinstance(baseline[key], (int, float))
        and isinstance(candidate[key], (int, float))
    }


def main():
    parser = argparse.ArgumentParser(description="网格风控参数敏感性实验")
    parser.add_argument("--stocks", default="数据模块/hs300_prescreen_30.txt")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--source-config", default="1_策略配置")
    parser.add_argument(
        "--plans",
        default="宽松:3:60,中等:5:30,严格:10:20",
        help="逗号分隔的名称:最小间隔:冻结K线",
    )
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    output = args.output_dir or os.path.join(
        项目根目录, "10_实验记录", f"网格风控敏感性_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(output, exist_ok=True)
    source = os.path.abspath(args.source_config)
    cases = [("原网格基线", False, 0, 0)] + [
        (name, True, interval, freeze_bars)
        for name, interval, freeze_bars in 解析方案(args.plans)
    ]
    results = {}
    configs = {}
    for name, enabled, interval, freeze_bars in cases:
        config_dir = os.path.join(output, name)
        复制配置(source, config_dir)
        设置网格风控(config_dir, enabled, interval, freeze_bars)
        configs[name] = config_dir
        results[name] = 回测(config_dir, args.stocks, args.start, args.end, args.workers)
    baseline = results["原网格基线"]
    comparison = {
        name: 差异(summary, baseline)
        for name, summary in results.items()
        if name != "原网格基线"
    }
    payload = {
        "训练期": [args.start, args.end],
        "股票池": args.stocks,
        "结果": results,
        "相对原网格基线": comparison,
        "配置目录": configs,
    }
    with open(os.path.join(output, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False, indent=2)
    print(json.dumps({"输出目录": output, **payload}, ensure_ascii=False))


if __name__ == "__main__":
    main()
