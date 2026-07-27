#!/usr/bin/env python3
"""个股大周期趋势准入消融实验；只修改实验配置副本。"""

import argparse
import json
import os
from datetime import datetime

import yaml

from 研究实验.exit_rule_experiment import 复制配置
from 研究实验.grid_risk_limits_experiment import 回测


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def 设置趋势准入(config_dir, enabled=True):
    path = os.path.join(config_dir, "过滤因子配置.yaml")
    with open(path, encoding="utf-8") as source:
        config = yaml.safe_load(source) or {}
    item = next(row for row in config["过滤因子列表"]
                if row.get("英文标识") == "stock_trend_universe_filter")
    item["启用"] = bool(enabled)
    with open(path, "w", encoding="utf-8") as target:
        yaml.safe_dump(config, target, allow_unicode=True, sort_keys=False)

    path = os.path.join(config_dir, "模块开关配置.yaml")
    with open(path, encoding="utf-8") as source:
        switches = yaml.safe_load(source) or {}
    switches["模块类别"]["过滤因子"]["stock_trend_universe_filter"]["启用"] = bool(enabled)
    with open(path, "w", encoding="utf-8") as target:
        yaml.safe_dump(switches, target, allow_unicode=True, sort_keys=False)


def main():
    parser = argparse.ArgumentParser(description="个股趋势准入消融实验")
    parser.add_argument("--stocks", default="数据模块/hs300_prescreen_30.txt")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--source-config", default="1_策略配置")
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    output = args.output_dir or os.path.join(
        项目根目录, "10_实验记录", f"个股趋势准入消融_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(output, exist_ok=True)
    source = os.path.abspath(args.source_config)
    results = {}
    configs = {}
    for name, enabled in (("全量基线", False), ("启用个股趋势准入", True)):
        config_dir = os.path.join(output, name)
        复制配置(source, config_dir)
        设置趋势准入(config_dir, enabled)
        configs[name] = config_dir
        results[name] = 回测(config_dir, args.stocks, args.start, args.end, args.workers)
    baseline = results["全量基线"]
    candidate = results["启用个股趋势准入"]
    diff = {
        key: candidate[key] - baseline[key]
        for key in baseline.keys() & candidate.keys()
        if isinstance(baseline[key], (int, float)) and isinstance(candidate[key], (int, float))
    }
    payload = {"训练期": [args.start, args.end], "股票池": args.stocks,
               "结果": results, "启用减基线": diff, "配置目录": configs}
    with open(os.path.join(output, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False, indent=2)
    print(json.dumps({"输出目录": output, **payload}, ensure_ascii=False))


if __name__ == "__main__":
    main()
