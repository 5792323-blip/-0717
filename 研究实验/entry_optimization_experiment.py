#!/usr/bin/env python3
"""训练期买入结构实验：信号组合 -> 成交额阈值 -> 滚动分段复核。"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

import yaml

from 研究实验.exit_rule_experiment import 复制配置


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
全部信号 = ["rsi_cross_20", "rsi_cross_30", "rsi_cross_ma", "rsi_cross_70"]
信号方案 = {
    "全部信号": 全部信号,
    "仅RSI20": ["rsi_cross_20"],
    "RSI20+均线": ["rsi_cross_20", "rsi_cross_ma"],
    "RSI20+RSI70": ["rsi_cross_20", "rsi_cross_70"],
    "RSI20+均线+RSI70": ["rsi_cross_20", "rsi_cross_ma", "rsi_cross_70"],
}


def 读取yaml(path):
    with open(path, encoding="utf-8") as source:
        return yaml.safe_load(source)


def 保存yaml(path, data):
    with open(path, "w", encoding="utf-8") as target:
        yaml.safe_dump(data, target, allow_unicode=True, sort_keys=False)


def 设置方案(config_dir, enabled_signals, turnover_threshold=None):
    buy_path = os.path.join(config_dir, "买入信号配置.yaml")
    buy = 读取yaml(buy_path)
    enabled = set(enabled_signals)
    for item in buy["买入信号列表"]:
        item["启用"] = item["英文标识"] in enabled
    保存yaml(buy_path, buy)

    filter_path = os.path.join(config_dir, "过滤因子配置.yaml")
    filters = 读取yaml(filter_path)
    volume = next(
        item for item in filters["过滤因子列表"]
        if item["英文标识"] == "volume_spike_filter"
    )
    volume["启用"] = turnover_threshold is not None
    if turnover_threshold is not None:
        volume["最低成交额比率"] = float(turnover_threshold)
    保存yaml(filter_path, filters)


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
    return json.loads(result.stdout)["汇总"]


def 候选排序(summary, baseline):
    # 回撤不得显著高于基线；合格者按综合得分、收益、盈亏比排序。
    drawdown_limit = baseline.get("平均最大回撤", 0) * 1.02 + 1e-12
    qualified = summary.get("平均最大回撤", 999) <= drawdown_limit
    return (
        int(qualified),
        summary.get("综合得分", -999),
        summary.get("平均年化收益率", -999),
        summary.get("平均盈亏比", -999),
    )


def 写表(target, rows):
    target.write("|方案|综合得分|年化收益|最大回撤|胜率|盈亏比|交易数|\n")
    target.write("|---|---:|---:|---:|---:|---:|---:|\n")
    for name, summary in rows.items():
        target.write(
            f"|{name}|{summary.get('综合得分', 0):.4f}|"
            f"{summary.get('平均年化收益率', 0):.3%}|"
            f"{summary.get('平均最大回撤', 0):.3%}|"
            f"{summary.get('加权胜率', 0):.2%}|"
            f"{summary.get('平均盈亏比', 0):.3f}|"
            f"{summary.get('总交易数', 0)}|\n"
        )


def main():
    parser = argparse.ArgumentParser(description="训练期买入结构优化实验")
    parser.add_argument("--stocks", default="数据模块/hs300_prescreen_30.txt")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--source-config", default="1_策略配置")
    parser.add_argument("--thresholds", nargs="+", type=float, default=[0.6, 0.7, 0.8])
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    output_dir = args.output_dir or os.path.join(
        项目根目录, "10_实验记录",
        f"买入结构训练实验_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )
    os.makedirs(output_dir, exist_ok=True)
    source = os.path.abspath(args.source_config)

    signal_results = {}
    signal_configs = {}
    for name, signals in 信号方案.items():
        config_dir = os.path.join(output_dir, "信号组合", name)
        复制配置(source, config_dir)
        设置方案(config_dir, signals, None)
        signal_configs[name] = config_dir
        signal_results[name] = 回测(config_dir, args.stocks, args.start, args.end, args.workers)

    baseline = signal_results["全部信号"]
    best_signal_name = max(
        (name for name in signal_results if name != "全部信号"),
        key=lambda name: 候选排序(signal_results[name], baseline),
    )
    best_signals = 信号方案[best_signal_name]

    turnover_results = {"不过滤": signal_results[best_signal_name]}
    turnover_configs = {"不过滤": signal_configs[best_signal_name]}
    for threshold in args.thresholds:
        name = f"成交额比率≥{threshold:g}"
        config_dir = os.path.join(output_dir, "成交额阈值", name)
        复制配置(source, config_dir)
        设置方案(config_dir, best_signals, threshold)
        turnover_configs[name] = config_dir
        turnover_results[name] = 回测(config_dir, args.stocks, args.start, args.end, args.workers)

    turnover_baseline = turnover_results["不过滤"]
    best_turnover_name = max(
        turnover_results,
        key=lambda name: 候选排序(turnover_results[name], turnover_baseline),
    )
    best_config = turnover_configs[best_turnover_name]

    rolling_results = {}
    for period_name, start, end in [
        ("2020-2021", "2020-01-01", "2021-12-31"),
        ("2022-2023", "2022-01-01", "2023-12-31"),
    ]:
        rolling_results[period_name] = {
            "基线": 回测(signal_configs["全部信号"], args.stocks, start, end, args.workers),
            "候选": 回测(best_config, args.stocks, start, end, args.workers),
        }

    payload = {
        "训练期": [args.start, args.end],
        "验证期": "未读取",
        "股票池": args.stocks,
        "信号组合": signal_results,
        "入选信号方案": best_signal_name,
        "成交额阈值": turnover_results,
        "入选成交额方案": best_turnover_name,
        "滚动分段": rolling_results,
        "候选配置目录": best_config,
    }
    with open(os.path.join(output_dir, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False, indent=2)
    with open(os.path.join(output_dir, "中文报告.md"), "w", encoding="utf-8") as target:
        target.write("# 买入结构训练期实验\n\n")
        target.write(f"- 训练期：{args.start} 至 {args.end}\n- 验证期：未读取\n- 股票池：{args.stocks}\n\n")
        target.write("## 信号组合\n\n")
        写表(target, signal_results)
        target.write(f"\n入选信号方案：**{best_signal_name}**。\n\n")
        target.write("## 上一交易日成交额阈值\n\n")
        写表(target, turnover_results)
        target.write(f"\n入选成交额方案：**{best_turnover_name}**。\n\n")
        target.write("## 滚动分段复核\n\n")
        for period, results in rolling_results.items():
            target.write(f"### {period}\n\n")
            写表(target, results)
            target.write("\n")
        target.write("候选只来自训练期；正式配置未修改，封存验证期未读取。\n")
    print(json.dumps({"输出目录": output_dir, **payload}, ensure_ascii=False))


if __name__ == "__main__":
    main()
