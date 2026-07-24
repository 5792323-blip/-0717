#!/usr/bin/env python3
"""2020-2023年度×横截面分桶稳健信号筛选；严禁读取封存验证期。"""

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import yaml

from 研究实验.exit_rule_experiment import 复制配置
from 运行程序.run_backtest import 读取股票列表


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
信号定义 = [
    ("20", "rsi_cross_20"),
    ("30", "rsi_cross_30"),
    ("MA", "rsi_cross_ma"),
    ("70", "rsi_cross_70"),
]
年度 = [2020, 2021, 2022, 2023]


def 生成信号方案():
    plans = {}
    for mask in range(1, 1 << len(信号定义)):
        labels = [label for index, (label, _) in enumerate(信号定义) if mask & (1 << index)]
        identifiers = [identifier for index, (_, identifier) in enumerate(信号定义) if mask & (1 << index)]
        plans["+".join(labels)] = identifiers
    return plans


def 设置信号(config_dir, enabled_identifiers):
    path = os.path.join(config_dir, "买入信号配置.yaml")
    with open(path, encoding="utf-8") as source:
        config = yaml.safe_load(source)
    enabled = set(enabled_identifiers)
    for item in config["买入信号列表"]:
        item["启用"] = item["英文标识"] in enabled
    with open(path, "w", encoding="utf-8") as target:
        yaml.safe_dump(config, target, allow_unicode=True, sort_keys=False)


def 执行年度回测(task):
    plan_name, config_dir, stocks, year, workers, output_path = task
    command = [
        sys.executable, os.path.join(项目根目录, "运行程序", "run_backtest.py"),
        "--config", config_dir, "--stocks", stocks,
        "--start", f"{year}-01-01", "--end", f"{year}-12-31",
        "--capital", "20000000", "--liquidity-limit", "0.01",
        "--workers", str(workers), "--output", output_path,
    ]
    result = subprocess.run(
        command, cwd=项目根目录, check=True, capture_output=True, text=True,
    )
    return plan_name, year, json.loads(result.stdout)


def 安全平均(values):
    finite = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return sum(finite) / len(finite) if finite else 0.0


def 分桶摘要(report, bucket_by_stock, bucket_count):
    buckets = []
    details = [item for item in report["股票明细"] if "错误" not in item]
    for bucket in range(bucket_count):
        rows = [item for item in details if bucket_by_stock.get(item["股票代码"]) == bucket]
        trades = sum(item.get("卖出次数", 0) for item in rows)
        weighted_win = (
            sum(item.get("胜率", 0) * item.get("卖出次数", 0) for item in rows) / trades
            if trades else 0.0
        )
        buckets.append({
            "桶": bucket + 1,
            "股票数": len(rows),
            "交易数": trades,
            "平均年化收益率": 安全平均([item.get("年化收益率") for item in rows]),
            "平均最大回撤": 安全平均([item.get("最大回撤") for item in rows]),
            "加权胜率": weighted_win,
            "平均盈亏比": 安全平均([item.get("盈亏比") for item in rows]),
        })
    return buckets


def 评价方案(year_reports, bucket_by_stock, bucket_count=3, minimum_positive_cells=9):
    yearly = []
    cells = []
    for year in sorted(year_reports):
        report = year_reports[year]
        summary = report["汇总"]
        bucket_summaries = 分桶摘要(report, bucket_by_stock, bucket_count)
        yearly.append({"年度": year, **summary, "横截面分桶": bucket_summaries})
        cells.extend({"年度": year, **bucket} for bucket in bucket_summaries)

    annual_returns = [item.get("平均年化收益率", 0) for item in yearly]
    drawdowns = [item.get("平均最大回撤", 0) for item in yearly]
    win_rates = [item.get("加权胜率", 0) for item in yearly]
    ratios = [item.get("平均盈亏比", 0) for item in yearly]
    return_drawdowns = [
        annual / max(drawdown, 1e-9)
        for annual, drawdown in zip(annual_returns, drawdowns)
    ]
    positive_cells = sum(cell["平均年化收益率"] > 0 for cell in cells)
    yearly_trade_floor = min((item.get("总交易数", 0) for item in yearly), default=0)
    constraints = {
        "所有年度收益为正": all(value > 0 for value in annual_returns),
        "正收益横截面单元达标": positive_cells >= minimum_positive_cells,
        "各年度至少30笔交易": yearly_trade_floor >= 30,
        "年度平均盈亏比大于1": 安全平均(ratios) > 1.0,
    }
    robust_score = (
        0.45 * statistics.median(return_drawdowns)
        + 0.20 * min(return_drawdowns)
        + 0.15 * 安全平均(win_rates)
        + 0.20 * 安全平均(ratios)
        - 0.10 * (statistics.pstdev(return_drawdowns) if len(return_drawdowns) > 1 else 0.0)
    )
    return {
        "合格": all(constraints.values()),
        "硬约束": constraints,
        "稳健得分": robust_score,
        "平均年度收益": 安全平均(annual_returns),
        "最差年度收益": min(annual_returns),
        "平均年度回撤": 安全平均(drawdowns),
        "正收益年度数": sum(value > 0 for value in annual_returns),
        "正收益横截面单元数": positive_cells,
        "横截面单元总数": len(cells),
        "年度": yearly,
    }


def 排名键(item):
    result = item[1]
    passed_constraints = sum(result["硬约束"].values())
    return (
        int(result["合格"]),
        passed_constraints,
        result["正收益年度数"],
        result["正收益横截面单元数"],
        result["最差年度收益"],
        result["稳健得分"],
    )


def main():
    parser = argparse.ArgumentParser(description="稳健信号年度滚动筛选")
    parser.add_argument("--stocks", default="数据模块/hs300_prescreen_30.txt")
    parser.add_argument("--source-config", default="1_策略配置")
    parser.add_argument("--workers-per-backtest", type=int, default=2)
    parser.add_argument("--parallel-backtests", type=int, default=4)
    parser.add_argument("--bucket-count", type=int, default=3)
    parser.add_argument("--minimum-positive-cells", type=int, default=9)
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    output_dir = args.output_dir or os.path.join(
        项目根目录, "10_实验记录",
        f"稳健信号滚动训练_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )
    os.makedirs(output_dir, exist_ok=True)
    source = os.path.abspath(args.source_config)
    plans = 生成信号方案()
    stocks = 读取股票列表(args.stocks)
    bucket_by_stock = {stock: index % args.bucket_count for index, stock in enumerate(stocks)}

    plan_configs = {}
    tasks = []
    for plan_name, identifiers in plans.items():
        config_dir = os.path.join(output_dir, "配置", plan_name)
        复制配置(source, config_dir)
        设置信号(config_dir, identifiers)
        plan_configs[plan_name] = config_dir
        for year in 年度:
            result_path = os.path.join(output_dir, "年度结果", plan_name, f"{year}.json")
            os.makedirs(os.path.dirname(result_path), exist_ok=True)
            tasks.append((
                plan_name, config_dir, args.stocks, year,
                args.workers_per_backtest, result_path,
            ))

    year_reports = {name: {} for name in plans}
    with ThreadPoolExecutor(max_workers=args.parallel_backtests) as executor:
        future_map = {executor.submit(执行年度回测, task): task for task in tasks}
        for future in as_completed(future_map):
            plan_name, year, report = future.result()
            year_reports[plan_name][year] = report

    evaluations = {
        name: 评价方案(reports, bucket_by_stock, args.bucket_count, args.minimum_positive_cells)
        for name, reports in year_reports.items()
    }
    ranked = sorted(evaluations.items(), key=排名键, reverse=True)
    qualified = [name for name, result in ranked if result["合格"]]
    payload = {
        "训练期": ["2020-01-01", "2023-12-31"],
        "封存验证期": "未读取",
        "股票池": args.stocks,
        "股票数": len(stocks),
        "分桶规则": f"股票列表按顺序轮转分为{args.bucket_count}桶",
        "最低正收益单元要求": args.minimum_positive_cells,
        "方案数": len(plans),
        "合格方案": qualified,
        "排名": [name for name, _ in ranked],
        "结果": evaluations,
        "配置目录": plan_configs,
    }
    with open(os.path.join(output_dir, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False, indent=2)
    with open(os.path.join(output_dir, "中文报告.md"), "w", encoding="utf-8") as target:
        target.write("# 稳健信号年度滚动训练\n\n")
        target.write("- 数据：2020-2023训练期；2024-2026封存验证未读取。\n")
        target.write(f"- 股票：{len(stocks)}只，轮转分为{args.bucket_count}个横截面桶。\n")
        target.write("- 硬约束：4个年度平均收益全部为正；12个年度×股票桶中至少9个为正；每年至少30笔交易；年度平均盈亏比>1。\n\n")
        target.write("|排名|信号组合|合格|稳健得分|平均年度收益|最差年度收益|正收益年度|正收益单元|平均回撤|\n")
        target.write("|---:|---|---|---:|---:|---:|---:|---:|---:|\n")
        for rank, (name, result) in enumerate(ranked, 1):
            target.write(
                f"|{rank}|{name}|{'是' if result['合格'] else '否'}|{result['稳健得分']:.4f}|"
                f"{result['平均年度收益']:.3%}|{result['最差年度收益']:.3%}|"
                f"{result['正收益年度数']}/4|{result['正收益横截面单元数']}/{result['横截面单元总数']}|"
                f"{result['平均年度回撤']:.3%}|\n"
            )
        target.write("\n")
        if qualified:
            target.write(f"合格方案：{', '.join(qualified)}。只有这些方案可以进入共享资金训练复核。\n")
        else:
            target.write("没有方案通过全部硬约束。本轮不得强行选取排名第一的方案进入封存验证。\n")
    print(json.dumps({"输出目录": output_dir, "合格方案": qualified, "排名前五": ranked[:5]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
