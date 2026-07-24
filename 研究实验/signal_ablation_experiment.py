#!/usr/bin/env python3
"""在训练期逐一关闭买入信号，评估各信号的边际贡献。"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

import yaml

from 研究实验.exit_rule_experiment import 复制配置


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
信号列表 = [
    ("RSI上穿20", "rsi_cross_20"),
    ("RSI上穿30", "rsi_cross_30"),
    ("RSI上穿均线", "rsi_cross_ma"),
    ("RSI上穿70", "rsi_cross_70"),
]


def 设置关闭信号(config_dir, disabled_identifier=None):
    path = os.path.join(config_dir, "买入信号配置.yaml")
    with open(path, encoding="utf-8") as source:
        config = yaml.safe_load(source)
    for item in config["买入信号列表"]:
        item["启用"] = item["英文标识"] != disabled_identifier
    with open(path, "w", encoding="utf-8") as target:
        yaml.safe_dump(config, target, allow_unicode=True, sort_keys=False)


def 回测(config_dir, stocks, start, end, workers):
    command = [
        sys.executable,
        os.path.join(项目根目录, "运行程序", "run_backtest.py"),
        "--config", config_dir,
        "--stocks", stocks,
        "--start", start,
        "--end", end,
        "--capital", "20000000",
        "--liquidity-limit", "0.01",
        "--workers", str(workers),
    ]
    result = subprocess.run(
        command, cwd=项目根目录, check=True, capture_output=True, text=True
    )
    return json.loads(result.stdout)["汇总"]


def main():
    parser = argparse.ArgumentParser(description="买入信号训练期消融实验")
    parser.add_argument("--stocks", default="数据模块/hs300_prescreen_30.txt")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--source-config", default="1_策略配置")
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    output_dir = args.output_dir or os.path.join(
        项目根目录,
        "10_实验记录",
        f"买入信号消融训练实验_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )
    os.makedirs(output_dir, exist_ok=True)
    source = os.path.abspath(args.source_config)
    results = {}

    plans = [("全部信号", None)] + [(f"关闭{name}", identifier) for name, identifier in 信号列表]
    for name, disabled_identifier in plans:
        config_dir = os.path.join(output_dir, name)
        复制配置(source, config_dir)
        设置关闭信号(config_dir, disabled_identifier)
        results[name] = 回测(config_dir, args.stocks, args.start, args.end, args.workers)

    payload = {
        "训练期": [args.start, args.end],
        "验证期": "未读取",
        "股票池": args.stocks,
        "结果": results,
    }
    with open(os.path.join(output_dir, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False, indent=2)
    with open(os.path.join(output_dir, "中文报告.md"), "w", encoding="utf-8") as target:
        target.write("# 买入信号训练期消融实验\n\n")
        target.write(f"- 训练期：{args.start} 至 {args.end}\n- 验证期：未读取\n- 股票池：{args.stocks}\n\n")
        target.write("| 方案 | 综合得分 | 年化收益 | 最大回撤 | 胜率 | 盈亏比 | 交易数 |\n")
        target.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for name, summary in results.items():
            target.write(
                f"| {name} | {summary.get('综合得分', 0):.4f} | "
                f"{summary.get('平均年化收益率', 0):.2%} | "
                f"{summary.get('平均最大回撤', 0):.2%} | "
                f"{summary.get('加权胜率', 0):.2%} | "
                f"{summary.get('平均盈亏比', 0):.3f} | "
                f"{summary.get('总交易数', 0)} |\n"
            )
    print(json.dumps({"输出目录": output_dir, "结果": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
