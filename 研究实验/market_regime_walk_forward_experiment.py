#!/usr/bin/env python3
"""沪深300市场状态过滤的Walk-forward验证。"""

import argparse
import json
import os
from datetime import datetime

import yaml

from 研究实验.exit_rule_experiment import 复制配置
from 研究实验.grid_risk_limits_experiment import 回测
from 研究实验.validation_protocol import 生成_walk_forward区间


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def 设置市场状态(config_dir, enabled=True):
    path = os.path.join(config_dir, "过滤因子配置.yaml")
    with open(path, encoding="utf-8") as source:
        config = yaml.safe_load(source) or {}
    item = next(row for row in config["过滤因子列表"]
                if row.get("英文标识") == "market_regime_filter")
    item["启用"] = bool(enabled)
    with open(path, "w", encoding="utf-8") as target:
        yaml.safe_dump(config, target, allow_unicode=True, sort_keys=False)
    path = os.path.join(config_dir, "模块开关配置.yaml")
    with open(path, encoding="utf-8") as source:
        switches = yaml.safe_load(source) or {}
    switches["模块类别"]["过滤因子"]["market_regime_filter"]["启用"] = bool(enabled)
    with open(path, "w", encoding="utf-8") as target:
        yaml.safe_dump(switches, target, allow_unicode=True, sort_keys=False)


def main():
    parser = argparse.ArgumentParser(description="市场状态过滤Walk-forward")
    parser.add_argument("--stocks", default="数据模块/hs300_prescreen_30.txt")
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default="2026-03-31")
    parser.add_argument("--train-years", type=int, default=2)
    parser.add_argument("--validation-years", type=int, default=1)
    parser.add_argument("--step-years", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--source-config", default="1_策略配置")
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    output = args.output_dir or os.path.join(
        项目根目录, "10_实验记录", f"市场状态WalkForward_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(output, exist_ok=True)
    source = os.path.abspath(args.source_config)
    results = {}
    windows = 生成_walk_forward区间(
        args.start, args.end, args.train_years, args.validation_years, args.step_years
    )
    for index, window in enumerate(windows, 1):
        start, end = window["验证期"]
        row = {}
        for name, enabled in (("完整基线", False), ("启用市场状态过滤", True)):
            config_dir = os.path.join(output, f"窗口{index}", name)
            复制配置(source, config_dir)
            设置市场状态(config_dir, enabled)
            row[name] = 回测(config_dir, args.stocks, start, end, args.workers)
        results[f"窗口{index}_{start[:4]}"] = {
            "训练期": window["训练期"], "验证期": window["验证期"], "结果": row,
        }
    payload = {"方案": "沪深300市场状态过滤", "股票池": args.stocks, "结果": results}
    with open(os.path.join(output, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False, indent=2)
    print(json.dumps({"输出目录": output, **payload}, ensure_ascii=False))


if __name__ == "__main__":
    main()
