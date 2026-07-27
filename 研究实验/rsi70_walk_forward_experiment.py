#!/usr/bin/env python3
"""RSI70关闭方案的Walk-forward验证；不修改正式策略配置。"""

import argparse
import json
import os
from datetime import datetime

import yaml

from 研究实验.exit_rule_experiment import 复制配置
from 研究实验.signal_ablation_experiment import 回测
from 研究实验.validation_protocol import 评估Walk_forward, 生成_walk_forward区间


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def 设置关闭_rsi70(config_dir):
    signal_path = os.path.join(config_dir, "买入信号配置.yaml")
    with open(signal_path, encoding="utf-8") as source:
        signals = yaml.safe_load(source) or {}
    for item in signals.get("买入信号列表", []):
        if item.get("英文标识") == "rsi_cross_70":
            item["启用"] = False
    with open(signal_path, "w", encoding="utf-8") as target:
        yaml.safe_dump(signals, target, allow_unicode=True, sort_keys=False)

    switch_path = os.path.join(config_dir, "模块开关配置.yaml")
    with open(switch_path, encoding="utf-8") as source:
        switches = yaml.safe_load(source) or {}
    item = switches["模块类别"]["买入规则"]["rsi_cross_70"]
    item["启用"] = False
    with open(switch_path, "w", encoding="utf-8") as target:
        yaml.safe_dump(switches, target, allow_unicode=True, sort_keys=False)


def 运行方案(source, output, stocks, start, end, workers, disable_rsi70):
    复制配置(source, output)
    if disable_rsi70:
        设置关闭_rsi70(output)
    return 回测(output, stocks, start, end, workers)


def main():
    parser = argparse.ArgumentParser(description="RSI70 Walk-forward验证")
    parser.add_argument("--stocks", default="数据模块/hs300_prescreen_30.txt")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2026-03-31")
    parser.add_argument("--train-years", type=int, default=2)
    parser.add_argument("--validation-years", type=int, default=1)
    parser.add_argument("--step-years", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--source-config", default="1_策略配置")
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    output = args.output_dir or os.path.join(
        项目根目录, "10_实验记录", f"RSI70WalkForward_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(output, exist_ok=True)
    source = os.path.abspath(args.source_config)
    windows = 生成_walk_forward区间(
        args.start, args.end, args.train_years, args.validation_years, args.step_years
    )
    results = {}
    for index, window in enumerate(windows, 1):
        validation_start, validation_end = window["验证期"]
        window_dir = os.path.join(output, f"窗口{index}")
        baseline = 运行方案(
            source, os.path.join(window_dir, "全部信号"), args.stocks,
            validation_start, validation_end, args.workers, False,
        )
        candidate = 运行方案(
            source, os.path.join(window_dir, "关闭RSI70"), args.stocks,
            validation_start, validation_end, args.workers, True,
        )
        results[f"窗口{index}_{validation_start[:4]}"] = {
            "训练期": window["训练期"], "验证期": window["验证期"],
            "基线": baseline, "候选": candidate,
        }
    evaluation = 评估Walk_forward(results)
    payload = {
        "方案": "关闭RSI上穿70", "股票池": args.stocks,
        "结果": results, "Walk_forward评估": evaluation,
    }
    with open(os.path.join(output, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False, indent=2)
    print(json.dumps({"输出目录": output, **payload}, ensure_ascii=False))


if __name__ == "__main__":
    main()
