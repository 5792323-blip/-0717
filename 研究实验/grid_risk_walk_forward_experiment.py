#!/usr/bin/env python3
"""网格风控滚动验证；每个验证窗口只使用对应窗口之前选定的参数。"""

import argparse
import json
import os
from datetime import datetime

from 研究实验.exit_rule_experiment import 复制配置
from 研究实验.grid_risk_limits_experiment import 回测, 设置网格风控
from 研究实验.validation_protocol import 评估Walk_forward, 生成_walk_forward区间


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def 运行方案(source, output, stocks, start, end, workers, enabled):
    复制配置(source, output)
    设置网格风控(output, enabled, 3, 60)
    return 回测(output, stocks, start, end, workers)


def main():
    parser = argparse.ArgumentParser(description="网格风控Walk-forward验证")
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
        项目根目录, "10_实验记录", f"网格风控WalkForward_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
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
        baseline = 回测(
            (lambda path: (复制配置(source, path), path)[1])(
                os.path.join(window_dir, "原网格基线")
            ),
            args.stocks, validation_start, validation_end, args.workers,
        )
        candidate = 运行方案(
            source, os.path.join(window_dir, "宽松档_3_60"), args.stocks,
            validation_start, validation_end, args.workers, True,
        )
        results[f"窗口{index}_{validation_start[:4]}"] = {
            "训练期": window["训练期"], "验证期": window["验证期"],
            "基线": baseline, "候选": candidate,
        }
    evaluation = 评估Walk_forward(results)
    payload = {
        "参数": {"最小加仓间隔K线": 3, "禁止加仓持仓K线数": 60},
        "股票池": args.stocks, "结果": results, "Walk_forward评估": evaluation,
    }
    with open(os.path.join(output, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False, indent=2)
    print(json.dumps({"输出目录": output, **payload}, ensure_ascii=False))


if __name__ == "__main__":
    main()
