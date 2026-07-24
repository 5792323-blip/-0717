#!/usr/bin/env python3
"""强制执行“先诊断、后优化”的自动研究工作流。"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def 运行(command):
    return subprocess.run(command, cwd=项目根目录, check=True, text=True)


def main():
    parser = argparse.ArgumentParser(description="策略0717诊断与自动优化入口")
    parser.add_argument("--stocks", default="数据模块/hs300_prescreen_30.txt")
    parser.add_argument("--full-stocks", default="数据模块/hs300_list.txt")
    parser.add_argument("--trials", type=int, default=200)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_dir = os.path.join(项目根目录, "10_实验记录", f"自动优化_{timestamp}")
    diagnosis_dir = os.path.join(experiment_dir, "诊断阶段")
    os.makedirs(diagnosis_dir, exist_ok=True)

    # 当前本地数据最早为2020-01-02；2015-2019缺失会在诊断报告中明确记录。
    运行([
        sys.executable, os.path.join("分析工具", "loss_analyzer.py"),
        "--stocks", args.full_stocks,
        "--start", "2020-01-01",
        "--end", "2023-12-31",
        "--workers", str(args.workers),
        "--output-dir", diagnosis_dir,
    ])
    运行([
        sys.executable, os.path.join("优化工具", "auto_optimize.py"),
        "--stocks", args.stocks,
        "--full-stocks", args.full_stocks,
        "--trials", str(args.trials),
        "--rounds", str(args.rounds),
        "--top-k", str(args.top_k),
        "--workers", str(args.workers),
        "--threshold", "0.8",
        "--train-start", "2020-01-01",
        "--train-end", "2023-12-31",
        "--validation-start", "2024-01-01",
        "--validation-end", "2026-07-01",
        "--experiment-dir", experiment_dir,
    ])
    print(json.dumps({"实验目录": experiment_dir}, ensure_ascii=False))


if __name__ == "__main__":
    main()
