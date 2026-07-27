#!/usr/bin/env python3
"""严格个股趋势准入的Walk-forward验证。"""

import argparse
import json
import os
from datetime import datetime

import yaml

from 研究实验.exit_rule_experiment import 复制配置
from 研究实验.grid_risk_limits_experiment import 回测
from 研究实验.stock_trend_filter_experiment import 设置趋势准入
from 研究实验.validation_protocol import 生成_walk_forward区间


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
严格阈值 = {"长均线下偏离上限": 0.05, "短中均线偏离上限": 0.03,
           "长均线斜率下限": 0.00, "中期高点回撤上限": 0.20}


def 设置严格阈值(config_dir):
    path = os.path.join(config_dir, "过滤因子配置.yaml")
    with open(path, encoding="utf-8") as source:
        config = yaml.safe_load(source) or {}
    item = next(row for row in config["过滤因子列表"]
                if row.get("英文标识") == "stock_trend_universe_filter")
    item.update(严格阈值)
    with open(path, "w", encoding="utf-8") as target:
        yaml.safe_dump(config, target, allow_unicode=True, sort_keys=False)


def 运行方案(source, output, stocks, start, end, workers, enabled):
    复制配置(source, output)
    设置趋势准入(output, enabled)
    if enabled:
        设置严格阈值(output)
    return 回测(output, stocks, start, end, workers)


def main():
    parser = argparse.ArgumentParser(description="严格个股趋势准入Walk-forward")
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
        项目根目录, "10_实验记录", f"个股趋势准入WalkForward_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(output, exist_ok=True)
    source = os.path.abspath(args.source_config)
    windows = 生成_walk_forward区间(
        args.start, args.end, args.train_years, args.validation_years, args.step_years
    )
    results = {}
    for index, window in enumerate(windows, 1):
        start, end = window["验证期"]
        baseline = 运行方案(source, os.path.join(output, f"窗口{index}", "全量基线"),
                            args.stocks, start, end, args.workers, False)
        candidate = 运行方案(source, os.path.join(output, f"窗口{index}", "严格趋势准入"),
                             args.stocks, start, end, args.workers, True)
        results[f"窗口{index}_{start[:4]}"] = {
            "训练期": window["训练期"], "验证期": window["验证期"],
            "基线": baseline, "候选": candidate,
        }
    payload = {"方案": "严格个股趋势准入", "参数": 严格阈值,
               "股票池": args.stocks, "结果": results}
    with open(os.path.join(output, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False, indent=2)
    print(json.dumps({"输出目录": output, **payload}, ensure_ascii=False))


if __name__ == "__main__":
    main()
