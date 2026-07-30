#!/usr/bin/env python3
"""按每个披露日计算个股历史评分，禁止使用未来快照。"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from 基本面.计算个股评分 import 计算评分


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", default="数据模块/基本面历史快照_2020_2026.csv")
    parser.add_argument("--output", default="基本面/个股历史评分结果.csv")
    parser.add_argument("--config", default="基本面/个股评分配置.yaml")
    args = parser.parse_args()

    frame = pd.read_csv(args.input, dtype=str, keep_default_na=False)
    for column in ("实际披露日", "评分日期"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    frame = frame.dropna(subset=["股票代码", "实际披露日", "评分日期"])
    frame = frame[frame["实际披露日"] <= frame["评分日期"]].copy()
    with open(args.config, encoding="utf-8") as source:
        config = yaml.safe_load(source) or {}

    outputs = []
    for _, group in frame.groupby("评分日期", sort=True):
        outputs.append(计算评分(group, config))
    result = pd.concat(outputs, ignore_index=True) if outputs else pd.DataFrame()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False, encoding="utf-8-sig")
    print({"输出": args.output, "行数": len(result), "评分日期数": int(result["评分日期"].nunique()) if not result.empty else 0})


if __name__ == "__main__":
    main()
