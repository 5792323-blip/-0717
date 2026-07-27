#!/usr/bin/env python3
"""RSI70关闭与市场状态自适应组合的Walk-forward验证。"""

import argparse
import json
import os
from datetime import datetime

import yaml

from 研究实验.exit_rule_experiment import 复制配置
from 研究实验.rsi70_walk_forward_experiment import 设置关闭_rsi70
from 研究实验.signal_ablation_experiment import 回测
from 研究实验.validation_protocol import 生成_walk_forward区间


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def 设置自适应(config_dir):
    path = os.path.join(config_dir, "过滤因子配置.yaml")
    with open(path, encoding="utf-8") as source:
        config = yaml.safe_load(source) or {}
    item = next(row for row in config["过滤因子列表"]
                if row.get("英文标识") == "rsi_regime_adaptive_filter")
    item["启用"] = True
    with open(path, "w", encoding="utf-8") as target:
        yaml.safe_dump(config, target, allow_unicode=True, sort_keys=False)

    path = os.path.join(config_dir, "模块开关配置.yaml")
    with open(path, encoding="utf-8") as source:
        switches = yaml.safe_load(source) or {}
    switches["模块类别"]["过滤因子"]["rsi_regime_adaptive_filter"]["启用"] = True
    with open(path, "w", encoding="utf-8") as target:
        yaml.safe_dump(switches, target, allow_unicode=True, sort_keys=False)


def 运行方案(source, output, stocks, start, end, workers, disable_rsi70, adaptive):
    复制配置(source, output)
    if disable_rsi70:
        设置关闭_rsi70(output)
    if adaptive:
        设置自适应(output)
    return 回测(output, stocks, start, end, workers)


def main():
    parser = argparse.ArgumentParser(description="RSI市场状态自适应Walk-forward验证")
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
        项目根目录, "10_实验记录", f"RSI70自适应WalkForward_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(output, exist_ok=True)
    windows = 生成_walk_forward区间(
        args.start, args.end, args.train_years, args.validation_years, args.step_years
    )
    source = os.path.abspath(args.source_config)
    plans = [("完整基线", False, False), ("关闭RSI70", True, False),
             ("关闭RSI70_开启自适应", True, True)]
    results = {}
    for index, window in enumerate(windows, 1):
        start, end = window["验证期"]
        window_results = {}
        for name, disable_rsi70, adaptive in plans:
            window_results[name] = 运行方案(
                source, os.path.join(output, f"窗口{index}", name), args.stocks,
                start, end, args.workers, disable_rsi70, adaptive,
            )
        results[f"窗口{index}_{start[:4]}"] = {
            "训练期": window["训练期"], "验证期": window["验证期"],
            "结果": window_results,
        }
    payload = {"方案": "关闭RSI70 + RSI市场状态自适应", "股票池": args.stocks,
               "参数": {"短均线周期": 20, "长均线周期": 60}, "结果": results}
    with open(os.path.join(output, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False, indent=2)
    print(json.dumps({"输出目录": output, **payload}, ensure_ascii=False))


if __name__ == "__main__":
    main()
