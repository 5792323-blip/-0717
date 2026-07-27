#!/usr/bin/env python3
"""RSI市场状态自适应均线参数敏感性实验。"""

import argparse
import json
import os
from datetime import datetime

import yaml

from 研究实验.exit_rule_experiment import 复制配置
from 研究实验.rsi70_walk_forward_experiment import 设置关闭_rsi70
from 研究实验.signal_ablation_experiment import 回测


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def 设置自适应周期(config_dir, fast, slow):
    path = os.path.join(config_dir, "过滤因子配置.yaml")
    with open(path, encoding="utf-8") as source:
        config = yaml.safe_load(source) or {}
    item = next(row for row in config["过滤因子列表"]
                if row.get("英文标识") == "rsi_regime_adaptive_filter")
    item["启用"] = True
    item["短均线周期"] = int(fast)
    item["长均线周期"] = int(slow)
    with open(path, "w", encoding="utf-8") as target:
        yaml.safe_dump(config, target, allow_unicode=True, sort_keys=False)

    path = os.path.join(config_dir, "模块开关配置.yaml")
    with open(path, encoding="utf-8") as source:
        switches = yaml.safe_load(source) or {}
    switches["模块类别"]["过滤因子"]["rsi_regime_adaptive_filter"]["启用"] = True
    with open(path, "w", encoding="utf-8") as target:
        yaml.safe_dump(switches, target, allow_unicode=True, sort_keys=False)


def 解析方案(text):
    return [(int(fast), int(slow)) for fast, slow in
            (item.split(":") for item in text.split(","))]


def main():
    parser = argparse.ArgumentParser(description="RSI自适应参数敏感性实验")
    parser.add_argument("--stocks", default="数据模块/hs300_prescreen_30.txt")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--source-config", default="1_策略配置")
    parser.add_argument("--plans", default="10:40,20:60,30:90")
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    output = args.output_dir or os.path.join(
        项目根目录, "10_实验记录", f"RSI自适应敏感性_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(output, exist_ok=True)
    source = os.path.abspath(args.source_config)
    results = {}
    configs = {}
    for fast, slow in 解析方案(args.plans):
        name = f"关闭RSI70_自适应{fast}_{slow}"
        config_dir = os.path.join(output, name)
        复制配置(source, config_dir)
        设置关闭_rsi70(config_dir)
        设置自适应周期(config_dir, fast, slow)
        configs[name] = config_dir
        results[name] = 回测(config_dir, args.stocks, args.start, args.end, args.workers)
    payload = {
        "训练期": [args.start, args.end], "股票池": args.stocks,
        "参数方案": [{"短均线周期": fast, "长均线周期": slow}
                     for fast, slow in 解析方案(args.plans)],
        "结果": results, "配置目录": configs,
    }
    with open(os.path.join(output, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False, indent=2)
    print(json.dumps({"输出目录": output, **payload}, ensure_ascii=False))


if __name__ == "__main__":
    main()
