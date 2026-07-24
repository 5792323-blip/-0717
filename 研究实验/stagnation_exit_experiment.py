#!/usr/bin/env python3
"""训练期真实成本回测无效交易退出，不读取验证期。"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

import yaml

from 研究实验.exit_rule_experiment import 复制配置


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def 设置规则(config_dir, enabled, bars=4, minimum_mfe=0.005):
    path = os.path.join(config_dir, "卖出规则配置.yaml")
    with open(path, encoding="utf-8") as source:
        config = yaml.safe_load(source)
    item = next(
        (row for row in config["卖出条件列表"]
         if row["英文标识"] == "stagnation_exit"),
        None,
    )
    if item is None:
        item = {
            "名称": "无效交易退出",
            "英文标识": "stagnation_exit",
            "检查顺序": 1,
            "说明": "持仓早期未产生最低浮盈且仍亏损时，下一根可交易K线开盘退出",
        }
        config["卖出条件列表"].insert(0, item)
    item["启用"] = bool(enabled)
    item["检查K线数"] = int(bars)
    item["最低MFE"] = float(minimum_mfe)
    with open(path, "w", encoding="utf-8") as target:
        yaml.safe_dump(config, target, allow_unicode=True, sort_keys=False)


def 回测(config_dir, stocks, start, end, workers):
    result = subprocess.run(
        [
            sys.executable, os.path.join(项目根目录, "运行程序", "run_backtest.py"),
            "--config", config_dir, "--stocks", stocks,
            "--start", start, "--end", end,
            "--capital", "20000000", "--liquidity-limit", "0.01",
            "--workers", str(workers),
        ],
        cwd=项目根目录, check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)["汇总"]


def 排序(summary, baseline):
    drawdown_limit = baseline.get("平均最大回撤", 0) * 1.02 + 1e-12
    return (
        int(summary.get("平均最大回撤", 999) <= drawdown_limit),
        summary.get("综合得分", -999),
        summary.get("平均年化收益率", -999),
    )


def 写表(target, results):
    target.write("|方案|综合得分|年化收益|最大回撤|胜率|盈亏比|交易数|\n")
    target.write("|---|---:|---:|---:|---:|---:|---:|\n")
    for name, s in results.items():
        target.write(
            f"|{name}|{s.get('综合得分', 0):.4f}|{s.get('平均年化收益率', 0):.3%}|"
            f"{s.get('平均最大回撤', 0):.3%}|{s.get('加权胜率', 0):.2%}|"
            f"{s.get('平均盈亏比', 0):.3f}|{s.get('总交易数', 0)}|\n"
        )


def main():
    parser = argparse.ArgumentParser(description="无效交易退出训练实验")
    parser.add_argument("--stocks", default="数据模块/hs300_prescreen_30.txt")
    parser.add_argument("--source-config", required=True)
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--bars", nargs="+", type=int, default=[4, 8, 12])
    parser.add_argument("--minimum-mfe", type=float, default=0.005)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    output_dir = args.output_dir or os.path.join(
        项目根目录, "10_实验记录",
        f"无效交易退出训练实验_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )
    os.makedirs(output_dir, exist_ok=True)
    source = os.path.abspath(args.source_config)
    configs = {}
    results = {}

    baseline_dir = os.path.join(output_dir, "基线")
    复制配置(source, baseline_dir)
    设置规则(baseline_dir, False)
    configs["基线"] = baseline_dir
    results["基线"] = 回测(baseline_dir, args.stocks, args.start, args.end, args.workers)
    for bars in args.bars:
        name = f"{bars}根无效交易退出"
        config_dir = os.path.join(output_dir, name)
        复制配置(source, config_dir)
        设置规则(config_dir, True, bars, args.minimum_mfe)
        configs[name] = config_dir
        results[name] = 回测(config_dir, args.stocks, args.start, args.end, args.workers)

    baseline = results["基线"]
    best_name = max(results, key=lambda name: 排序(results[name], baseline))
    rolling = {}
    for period, start, end in [
        ("2020-2021", "2020-01-01", "2021-12-31"),
        ("2022-2023", "2022-01-01", "2023-12-31"),
    ]:
        rolling[period] = {
            "基线": 回测(configs["基线"], args.stocks, start, end, args.workers),
            "候选": 回测(configs[best_name], args.stocks, start, end, args.workers),
        }

    payload = {
        "训练期": [args.start, args.end], "验证期": "未读取",
        "股票池": args.stocks, "最低MFE": args.minimum_mfe,
        "结果": results, "入选方案": best_name,
        "候选配置目录": configs[best_name], "滚动分段": rolling,
    }
    with open(os.path.join(output_dir, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False, indent=2)
    with open(os.path.join(output_dir, "中文报告.md"), "w", encoding="utf-8") as target:
        target.write("# 无效交易退出训练实验\n\n")
        target.write(f"- 训练期：{args.start} 至 {args.end}\n- 验证期：未读取\n- 最低MFE：{args.minimum_mfe:.2%}\n\n")
        写表(target, results)
        target.write(f"\n入选方案：**{best_name}**。\n\n## 滚动分段\n\n")
        for period, period_results in rolling.items():
            target.write(f"### {period}\n\n")
            写表(target, period_results)
            target.write("\n")
    print(json.dumps({"输出目录": output_dir, **payload}, ensure_ascii=False))


if __name__ == "__main__":
    main()
