#!/usr/bin/env python3
"""训练期隔离验证波动率状态过滤，不读取验证集。"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

import yaml

from 研究实验.exit_rule_experiment import 复制配置


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def 设置过滤(config_dir, enabled, high_allowed, high_blocked=None):
    path = os.path.join(config_dir, "过滤因子配置.yaml")
    with open(path, encoding="utf-8") as source:
        config = yaml.safe_load(source)
    item = next(row for row in config["过滤因子列表"] if row["英文标识"] == "volatility_regime_filter")
    item["启用"] = enabled
    item["高波动允许信号"] = high_allowed if high_blocked is None else []
    item["高波动禁止信号"] = high_blocked or []
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
    parser = argparse.ArgumentParser(description="波动率状态过滤训练期实验")
    parser.add_argument("--stocks", default="600519")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--high-allowed", nargs="+", default=["RSI上穿20"])
    parser.add_argument("--high-blocked", nargs="+", help="使用禁止列表时，改为高波动禁止这些信号")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--source-config", default="1_策略配置")
    args = parser.parse_args()

    output_dir = os.path.join(
        项目根目录, "10_实验记录", f"波动率状态训练实验_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(output_dir, exist_ok=True)
    results = {}
    for name, enabled in [("关闭过滤", False), ("高波动状态过滤", True)]:
        config_dir = os.path.join(output_dir, name)
        复制配置(os.path.abspath(args.source_config), config_dir)
        设置过滤(config_dir, enabled, args.high_allowed, args.high_blocked)
        results[name] = 回测(config_dir, args.stocks, args.start, args.end, args.workers)
    with open(os.path.join(output_dir, "结果.json"), "w", encoding="utf-8") as target:
        json.dump({"训练期": [args.start, args.end], "验证期": "未读取", "结果": results}, target, ensure_ascii=False, indent=2)
    with open(os.path.join(output_dir, "中文报告.md"), "w", encoding="utf-8") as target:
        target.write("# 波动率状态过滤训练期单因子实验\n\n")
        target.write(f"- 训练期：{args.start} 至 {args.end}\n- 验证期：未读取\n- 高波动允许信号：{args.high_allowed if args.high_blocked is None else '无'}\n- 高波动禁止信号：{args.high_blocked or '无'}\n\n")
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
