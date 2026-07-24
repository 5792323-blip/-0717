#!/usr/bin/env python3
"""在训练期隔离测试ATR跟踪退出倍数。"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

import yaml

from 研究实验.exit_rule_experiment import 复制配置


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def 设置ATR(config_dir, multiple):
    path = os.path.join(config_dir, "卖出规则配置.yaml")
    with open(path, encoding="utf-8") as source:
        config = yaml.safe_load(source)
    item = next(row for row in config["卖出条件列表"] if row["英文标识"] == "atr_trailing")
    item["启用"] = True
    item["ATR倍数"] = float(multiple)
    with open(path, "w", encoding="utf-8") as target:
        yaml.safe_dump(config, target, allow_unicode=True, sort_keys=False)


def 回测(config_dir, stocks, start, end, workers):
    command = [
        sys.executable, os.path.join(项目根目录, "运行程序", "run_backtest.py"),
        "--config", config_dir, "--stocks", stocks,
        "--start", start, "--end", end, "--capital", "20000000",
        "--liquidity-limit", "0.01", "--workers", str(workers),
    ]
    result = subprocess.run(command, cwd=项目根目录, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)["汇总"]


def main():
    parser = argparse.ArgumentParser(description="训练期ATR跟踪倍数敏感性实验")
    parser.add_argument("--stocks", default="600519")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--multiples", nargs="+", type=float, default=[1.5, 2.0, 2.5, 3.0, 3.5, 4.0])
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--source-config", default="10_实验记录/自动优化_20260722_022544/最终候选/最佳配置")
    args = parser.parse_args()

    output_dir = os.path.join(
        项目根目录, "10_实验记录", f"ATR退出训练实验_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(output_dir, exist_ok=True)
    results = {}
    for multiple in args.multiples:
        config_dir = os.path.join(output_dir, f"ATR_{multiple:g}")
        复制配置(os.path.abspath(args.source_config), config_dir)
        设置ATR(config_dir, multiple)
        results[f"ATR_{multiple:g}"] = 回测(config_dir, args.stocks, args.start, args.end, args.workers)
    with open(os.path.join(output_dir, "结果.json"), "w", encoding="utf-8") as target:
        json.dump({"训练期": [args.start, args.end], "验证期": "未读取", "结果": results}, target, ensure_ascii=False, indent=2)
    with open(os.path.join(output_dir, "中文报告.md"), "w", encoding="utf-8") as target:
        target.write("# ATR跟踪退出倍数训练期敏感性\n\n")
        target.write(f"- 训练期：{args.start} 至 {args.end}\n- 验证期：未读取\n\n")
        target.write("| 方案 | 综合得分 | 年化收益 | 最大回撤 | 胜率 | 盈亏比 |\n|---|---:|---:|---:|---:|---:|\n")
        for name, summary in results.items():
            target.write(
                f"| {name} | {summary.get('综合得分', 0):.4f} | {summary.get('平均年化收益率', 0):.2%} | "
                f"{summary.get('平均最大回撤', 0):.2%} | {summary.get('加权胜率', 0):.2%} | "
                f"{summary.get('平均盈亏比', 0):.3f} |\n"
            )
    print(json.dumps({"输出目录": output_dir, "结果": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
