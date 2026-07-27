#!/usr/bin/env python3
"""训练期网格风控参数对照；只修改实验配置，不修改正式配置。"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

import yaml

from 研究实验.exit_rule_experiment import 复制配置


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def 设置网格风控(config_dir, enabled, interval=5, freeze_bars=30):
    path = os.path.join(config_dir, "因子配置.yaml")
    with open(path, encoding="utf-8") as source:
        config = yaml.safe_load(source) or {}
    grid = config.setdefault("因子列表", {}).setdefault("grid_addon", {})
    params = grid.setdefault("参数", {})
    params["启用风控限制"] = bool(enabled)
    params["最小加仓间隔K线"] = int(interval)
    params["禁止加仓持仓K线数"] = int(freeze_bars)
    with open(path, "w", encoding="utf-8") as target:
        yaml.safe_dump(config, target, allow_unicode=True, sort_keys=False)


def 回测(config_dir, stocks, start, end, workers):
    result = subprocess.run([
        sys.executable, os.path.join(项目根目录, "运行程序", "run_backtest.py"),
        "--config", config_dir, "--stocks", stocks,
        "--start", start, "--end", end,
        "--capital", "20000000", "--liquidity-limit", "0.01",
        "--workers", str(workers),
    ], cwd=项目根目录, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)["汇总"]


def main():
    parser = argparse.ArgumentParser(description="网格风控限制训练期对照实验")
    parser.add_argument("--stocks", default="数据模块/hs300_prescreen_30.txt")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--interval", type=int, default=5)
    parser.add_argument("--freeze-bars", type=int, default=30)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--source-config", default="1_策略配置")
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    output = args.output_dir or os.path.join(
        项目根目录, "10_实验记录", f"网格风控训练实验_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(output, exist_ok=True)
    results = {}
    configs = {}
    for name, enabled in (("原网格基线", False), ("网格风控限制", True)):
        config_dir = os.path.join(output, name)
        复制配置(os.path.abspath(args.source_config), config_dir)
        设置网格风控(config_dir, enabled, args.interval, args.freeze_bars)
        configs[name] = config_dir
        results[name] = 回测(config_dir, args.stocks, args.start, args.end, args.workers)
    baseline = results["原网格基线"]
    candidate = results["网格风控限制"]
    diff = {
        key: candidate[key] - baseline[key]
        for key in baseline.keys() & candidate.keys()
        if isinstance(baseline[key], (int, float)) and isinstance(candidate[key], (int, float))
    }
    payload = {
        "训练期": [args.start, args.end], "验证期": "未读取",
        "股票池": args.stocks, "最小加仓间隔K线": args.interval,
        "禁止加仓持仓K线数": args.freeze_bars, "配置目录": configs,
        "结果": results, "风控限制减原网格": diff,
    }
    with open(os.path.join(output, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False, indent=2)
    print(json.dumps({"输出目录": output, **payload}, ensure_ascii=False))


if __name__ == "__main__":
    main()
