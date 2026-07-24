#!/usr/bin/env python3
"""仅RSI20下测试标准长期均线风险开关，使用年度×横截面硬约束。"""

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import yaml

from 研究实验.exit_rule_experiment import 复制配置
from 研究实验.robust_signal_walkforward import 评价方案
from 运行程序.run_backtest import 读取股票列表


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
年度 = [2020, 2021, 2022, 2023]


def 设置方案(config_dir, period=None):
    buy_path = os.path.join(config_dir, "买入信号配置.yaml")
    with open(buy_path, encoding="utf-8") as source:
        buy = yaml.safe_load(source)
    for item in buy["买入信号列表"]:
        item["启用"] = item["英文标识"] == "rsi_cross_20"
    with open(buy_path, "w", encoding="utf-8") as target:
        yaml.safe_dump(buy, target, allow_unicode=True, sort_keys=False)

    filter_path = os.path.join(config_dir, "过滤因子配置.yaml")
    with open(filter_path, encoding="utf-8") as source:
        filters = yaml.safe_load(source)
    item = next(row for row in filters["过滤因子列表"] if row["英文标识"] == "index_trend_filter")
    item["启用"] = period is not None
    if period is not None:
        item["均线周期"] = int(period)
    with open(filter_path, "w", encoding="utf-8") as target:
        yaml.safe_dump(filters, target, allow_unicode=True, sort_keys=False)


def 执行(task):
    name, config, stocks, year, workers, output = task
    result = subprocess.run(
        [
            sys.executable, os.path.join(项目根目录, "运行程序", "run_backtest.py"),
            "--config", config, "--stocks", stocks,
            "--start", f"{year}-01-01", "--end", f"{year}-12-31",
            "--capital", "20000000", "--liquidity-limit", "0.01",
            "--workers", str(workers), "--output", output,
        ],
        cwd=项目根目录, check=True, capture_output=True, text=True,
    )
    return name, year, json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description="长期趋势风险开关训练实验")
    parser.add_argument("--stocks", default="数据模块/hs300_prescreen_30.txt")
    parser.add_argument("--source-config", default="1_策略配置")
    parser.add_argument("--workers-per-backtest", type=int, default=2)
    parser.add_argument("--parallel-backtests", type=int, default=4)
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    output_dir = args.output_dir or os.path.join(
        项目根目录, "10_实验记录",
        f"长期趋势风险开关训练_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )
    os.makedirs(output_dir, exist_ok=True)
    plans = {"无趋势过滤": None, "MA60": 60, "MA120": 120, "MA200": 200}
    reports = {name: {} for name in plans}
    tasks = []
    for name, period in plans.items():
        config = os.path.join(output_dir, "配置", name)
        复制配置(os.path.abspath(args.source_config), config)
        设置方案(config, period)
        for year in 年度:
            output = os.path.join(output_dir, "年度结果", name, f"{year}.json")
            os.makedirs(os.path.dirname(output), exist_ok=True)
            tasks.append((name, config, args.stocks, year, args.workers_per_backtest, output))
    with ThreadPoolExecutor(max_workers=args.parallel_backtests) as executor:
        futures = [executor.submit(执行, task) for task in tasks]
        for future in as_completed(futures):
            name, year, report = future.result()
            reports[name][year] = report

    stocks = 读取股票列表(args.stocks)
    bucket_by_stock = {stock: index % 3 for index, stock in enumerate(stocks)}
    evaluations = {name: 评价方案(result, bucket_by_stock, 3, 9) for name, result in reports.items()}
    qualified = [name for name, result in evaluations.items() if result["合格"]]
    payload = {
        "训练期": ["2020-01-01", "2023-12-31"], "封存验证期": "未读取",
        "信号": "仅RSI20", "方案": evaluations, "合格方案": qualified,
    }
    with open(os.path.join(output_dir, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False, indent=2)
    with open(os.path.join(output_dir, "中文报告.md"), "w", encoding="utf-8") as target:
        target.write("# 沪深300长期趋势风险开关训练\n\n")
        target.write("- 仅RSI20；只使用2020-2023；封存验证未读取。\n")
        target.write("- 风险开关严格使用股票交易日前一完整指数日线。\n\n")
        target.write("|方案|合格|平均年度收益|最差年度收益|正收益年度|正收益单元|平均回撤|稳健得分|\n")
        target.write("|---|---|---:|---:|---:|---:|---:|---:|\n")
        for name, result in evaluations.items():
            target.write(
                f"|{name}|{'是' if result['合格'] else '否'}|{result['平均年度收益']:.3%}|"
                f"{result['最差年度收益']:.3%}|{result['正收益年度数']}/4|"
                f"{result['正收益横截面单元数']}/12|{result['平均年度回撤']:.3%}|"
                f"{result['稳健得分']:.4f}|\n"
            )
        target.write("\n")
        target.write(
            f"合格方案：{', '.join(qualified)}。\n" if qualified
            else "没有方案通过硬约束，不得进入封存验证。\n"
        )
    print(json.dumps({"输出目录": output_dir, **payload}, ensure_ascii=False))


if __name__ == "__main__":
    main()
