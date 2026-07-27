#!/usr/bin/env python3
"""在训练期隔离测试硬止损，不读取验证期数据。"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime

import yaml


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
配置文件列表 = [
    "买入信号配置.yaml", "卖出规则配置.yaml", "仓位配置.yaml",
    "参数配置.yaml", "过滤因子配置.yaml", "因子配置.yaml", "核心模块配置.yaml",
    "模块开关配置.yaml", "扩展因子模型.json",
]


def 复制配置(source, target):
    os.makedirs(target, exist_ok=True)
    for name in 配置文件列表:
        shutil.copy2(os.path.join(source, name), os.path.join(target, name))


def 设置硬止损(config_dir, enabled, multiple):
    path = os.path.join(config_dir, "卖出规则配置.yaml")
    with open(path, encoding="utf-8") as source:
        config = yaml.safe_load(source)
    item = next(row for row in config["卖出条件列表"] if row["英文标识"] == "stop_loss")
    item["启用"] = enabled
    item["止损倍数"] = float(multiple)
    with open(path, "w", encoding="utf-8") as target:
        yaml.safe_dump(config, target, allow_unicode=True, sort_keys=False)


def 回测(config_dir, stocks, start, end, workers):
    command = [
        sys.executable, os.path.join(项目根目录, "运行程序", "run_backtest.py"),
        "--config", config_dir, "--stocks", stocks,
        "--start", start, "--end", end,
        "--capital", "20000000", "--liquidity-limit", "0.01",
        "--workers", str(workers),
    ]
    result = subprocess.run(
        command, cwd=项目根目录, check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def 摘要(report):
    return report["汇总"]


def main():
    parser = argparse.ArgumentParser(description="训练期硬止损隔离实验")
    parser.add_argument("--stocks", default="600519")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--multiples", nargs="+", type=float, default=[2.0, 3.0, 4.0])
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--source-config", default="10_实验记录/自动优化_20260722_022544/最终候选/最佳配置")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(项目根目录, "10_实验记录", f"退出规则训练实验_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)
    source = os.path.abspath(args.source_config)
    results = {}

    baseline_dir = os.path.join(output_dir, "基线配置")
    复制配置(source, baseline_dir)
    设置硬止损(baseline_dir, False, args.multiples[0])
    results["关闭硬止损"] = 摘要(回测(baseline_dir, args.stocks, args.start, args.end, args.workers))

    for multiple in args.multiples:
        config_dir = os.path.join(output_dir, f"硬止损_{multiple:g}ATR")
        复制配置(source, config_dir)
        设置硬止损(config_dir, True, multiple)
        results[f"硬止损_{multiple:g}ATR"] = 摘要(
            回测(config_dir, args.stocks, args.start, args.end, args.workers)
        )

    with open(os.path.join(output_dir, "结果.json"), "w", encoding="utf-8") as target:
        json.dump({
            "训练期": [args.start, args.end],
            "股票池": args.stocks,
            "结果": results,
            "验证期": "未读取",
        }, target, ensure_ascii=False, indent=2)
    with open(os.path.join(output_dir, "中文报告.md"), "w", encoding="utf-8") as target:
        target.write("# 硬止损训练期隔离实验\n\n")
        target.write(f"- 训练期：{args.start} 至 {args.end}\n")
        target.write("- 验证期：未读取；本实验不用于验证集调参。\n\n")
        target.write("| 方案 | 综合得分 | 年化收益 | 最大回撤 | 胜率 | 盈亏比 |\n")
        target.write("|---|---:|---:|---:|---:|---:|\n")
        for name, summary in results.items():
            target.write(
                f"| {name} | {summary.get('综合得分', 0):.4f} | "
                f"{summary.get('平均年化收益率', 0):.2%} | "
                f"{summary.get('平均最大回撤', 0):.2%} | "
                f"{summary.get('加权胜率', 0):.2%} | "
                f"{summary.get('平均盈亏比', 0):.3f} |\n"
            )
    print(json.dumps({"输出目录": output_dir, "结果": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
