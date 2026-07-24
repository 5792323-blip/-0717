#!/usr/bin/env python3
"""单模块开/关消融回测：自动复制配置、只改一个开关、输出对照结果。"""

import argparse
import json
import os
import shutil
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime

import yaml

from 运行程序.run_backtest import 执行单股任务, 汇总结果, 读取股票列表
from 模块系统 import 模块开关管理器, 模块配置错误


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def 复制并设置模块(base_config, target_config, category, module_id, enabled):
    shutil.copytree(base_config, target_config, dirs_exist_ok=True)
    path = os.path.join(target_config, "模块开关配置.yaml")
    with open(path, encoding="utf-8") as source:
        config = yaml.safe_load(source)
    try:
        item = config["模块类别"][category][module_id]
    except KeyError as error:
        raise 模块配置错误(f"未找到模块 {category}.{module_id}") from error
    if enabled and item.get("状态") == "未就绪":
        raise 模块配置错误(f"{category}.{module_id}未就绪，不允许回测启用")
    item["启用"] = bool(enabled)
    with open(path, "w", encoding="utf-8") as target:
        yaml.safe_dump(config, target, allow_unicode=True, sort_keys=False)
    模块开关管理器(target_config).验证()
    return target_config


def 设置最大持仓数(config_dir, max_positions):
    if max_positions is None:
        return
    positions_path = os.path.join(config_dir, "仓位配置.yaml")
    with open(positions_path, encoding="utf-8") as source:
        positions = yaml.safe_load(source) or {}
    positions.setdefault("基准仓位", {})["最大总持仓数"] = int(max_positions)
    with open(positions_path, "w", encoding="utf-8") as target:
        yaml.safe_dump(positions, target, allow_unicode=True, sort_keys=False)

    parameters_path = os.path.join(config_dir, "参数配置.yaml")
    with open(parameters_path, encoding="utf-8") as source:
        parameters = yaml.safe_load(source) or {}
    parameters.setdefault("仓位参数", {})["最大持仓数"] = int(max_positions)
    with open(parameters_path, "w", encoding="utf-8") as target:
        yaml.safe_dump(parameters, target, allow_unicode=True, sort_keys=False)


def 运行(config_dir, stocks, start, end, capital, liquidity_limit, workers=1):
    tasks = [(stock, config_dir, start, end, capital, liquidity_limit) for stock in stocks]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            details = list(executor.map(执行单股任务, tasks))
    else:
        details = [执行单股任务(task) for task in tasks]
    return {"汇总": 汇总结果(details), "股票明细": details}


def 计算差异(closed, opened):
    """开启减关闭；只比较两边共有的数值型汇总指标。"""
    return {
        key: opened[key] - closed[key]
        for key in closed.keys() & opened.keys()
        if isinstance(closed[key], (int, float)) and isinstance(opened[key], (int, float))
    }


def main():
    parser = argparse.ArgumentParser(description="单模块消融回测")
    parser.add_argument("--config", default="1_策略配置")
    parser.add_argument("--category", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--stocks", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--capital", type=float, default=20_000_000)
    parser.add_argument("--liquidity-limit", type=float, default=0.01)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--max-positions", type=int)
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    output_dir = args.output_dir or os.path.join(
        项目根目录, "10_实验记录", f"模块消融_{args.module}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.join(output_dir, "配置_关闭")
    candidate = os.path.join(output_dir, "配置_开启")
    base_config = os.path.abspath(args.config)
    复制并设置模块(base_config, base, args.category, args.module, False)
    复制并设置模块(base_config, candidate, args.category, args.module, True)
    设置最大持仓数(base, args.max_positions)
    设置最大持仓数(candidate, args.max_positions)
    stocks = 读取股票列表(args.stocks)
    closed = 运行(base, stocks, args.start, args.end, args.capital, args.liquidity_limit, args.workers)
    opened = 运行(candidate, stocks, args.start, args.end, args.capital, args.liquidity_limit, args.workers)
    report = {
        "模块": f"{args.category}.{args.module}", "股票": stocks,
        "最大持仓数": args.max_positions,
        "并行进程数": args.workers,
        "区间": [args.start, args.end], "关闭": closed, "开启": opened,
        "开启减关闭": 计算差异(closed["汇总"], opened["汇总"]),
    }
    with open(os.path.join(output_dir, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(report, target, ensure_ascii=False, indent=2)
    print(json.dumps({
        "输出目录": output_dir, "模块": report["模块"],
        "关闭": report["关闭"]["汇总"], "开启": report["开启"]["汇总"],
        "开启减关闭": report["开启减关闭"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
