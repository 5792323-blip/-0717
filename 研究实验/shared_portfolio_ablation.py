#!/usr/bin/env python3
"""将两套策略信号放入同一共享资金账户，比较单模块开关效果。"""

import argparse
import json
import os
from datetime import datetime

import pandas as pd
import yaml

from 运行程序.run_backtest import 读取股票列表
from 组合回测.组合风险控制 import 读取交易成本, 运行独立信号, 重放组合


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def 读取仓位限制(config_dir, max_positions):
    with open(os.path.join(config_dir, "仓位配置.yaml"), encoding="utf-8") as source:
        base = (yaml.safe_load(source) or {}).get("基准仓位", {})
    return {
        "仓位倍数": 1.0,
        "单股上限": float(base.get("最大单只比例", 0.10)),
        "总暴露上限": float(base.get("最大总仓位比例", 0.98)),
        "现金底线": float(base.get("现金底线", 0.20)),
        "最大持仓数": int(max_positions),
    }


def 运行一侧(name, config, stocks, args, output_dir):
    costs = 读取交易成本(config)
    trades, prices, errors = 运行独立信号(
        stocks, config, args.start, args.end, args.capital, args.liquidity_limit, args.workers
    )
    limits = 读取仓位限制(config, args.max_positions)
    result = 重放组合(trades, prices, args.capital, limits, costs)
    curve = result.pop("权益曲线")
    pd.DataFrame(curve).to_csv(
        os.path.join(output_dir, f"{name}_权益曲线.csv"), index=False, encoding="utf-8-sig"
    )
    return {"配置": os.path.abspath(config), "有效股票数": len(prices), "错误": errors,
            "仓位限制": limits, "结果": result}


def 数值差异(base, candidate):
    return {key: candidate[key] - base[key] for key in base.keys() & candidate.keys()
            if isinstance(base[key], (int, float)) and isinstance(candidate[key], (int, float))}


def main():
    parser = argparse.ArgumentParser(description="共享资金单模块消融")
    parser.add_argument("--base-config", required=True)
    parser.add_argument("--candidate-config", required=True)
    parser.add_argument("--stocks", default="数据模块/hs300_list.txt")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--capital", type=float, default=20_000_000)
    parser.add_argument("--liquidity-limit", type=float, default=0.01)
    parser.add_argument("--max-positions", type=int, default=300)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    stocks = 读取股票列表(args.stocks)
    output_dir = args.output_dir or os.path.join(
        PROJECT_ROOT, "10_实验记录", f"共享资金模块消融_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(output_dir, exist_ok=True)
    base = 运行一侧("基线", args.base_config, stocks, args, output_dir)
    with open(os.path.join(output_dir, "基线.json"), "w", encoding="utf-8") as target:
        json.dump(base, target, ensure_ascii=False, indent=2)
    candidate = 运行一侧("候选", args.candidate_config, stocks, args, output_dir)
    with open(os.path.join(output_dir, "候选.json"), "w", encoding="utf-8") as target:
        json.dump(candidate, target, ensure_ascii=False, indent=2)
    report = {
        "区间": [args.start, args.end], "名单股票数": len(stocks), "最大持仓数": args.max_positions,
        "初始资金": args.capital, "基线": base, "候选": candidate,
        "候选减基线": 数值差异(base["结果"], candidate["结果"]),
    }
    with open(os.path.join(output_dir, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(report, target, ensure_ascii=False, indent=2)
    print(json.dumps({"输出目录": output_dir, "基线": base["结果"], "候选": candidate["结果"],
                      "候选减基线": report["候选减基线"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
