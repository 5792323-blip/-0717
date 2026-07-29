#!/usr/bin/env python3
"""审计个股基本面历史快照的时点、覆盖率和重复记录。"""

import argparse
import json
from pathlib import Path

import pandas as pd


REQUIRED = ["股票代码", "实际披露日", "评分日期", "数据来源", "数据状态"]
METRICS = [
    "ROE", "ROIC", "FCF净利比", "收入3年CAGR", "扣非净利润3年CAGR",
    "资产负债率", "利息保障倍数", "PE_TTM", "PB_MRQ", "EV_EBITDA", "FCF_Yield",
]


def audit(path):
    frame = path.copy() if isinstance(path, pd.DataFrame) else pd.read_csv(path, dtype=str, keep_default_na=False)
    issues = []
    missing = [column for column in REQUIRED if column not in frame.columns]
    if missing:
        issues.append({"类型": "缺少必需字段", "字段": missing})
        return {"通过": False, "行数": len(frame), "问题": issues}

    for column in ("实际披露日", "评分日期"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
        if frame[column].isna().any():
            issues.append({"类型": "日期无效", "字段": column, "数量": int(frame[column].isna().sum())})
    future = frame[frame["实际披露日"] > frame["评分日期"]]
    if not future.empty:
        issues.append({"类型": "未来数据", "数量": len(future)})

    duplicate = frame.duplicated(subset=["股票代码", "实际披露日"], keep=False)
    if duplicate.any():
        issues.append({"类型": "股票披露日重复", "数量": int(duplicate.sum())})

    for column in METRICS:
        if column not in frame.columns:
            issues.append({"类型": "缺少评分指标", "字段": column})
        elif pd.to_numeric(frame[column], errors="coerce").notna().sum() == 0:
            issues.append({"类型": "指标无有效数值", "字段": column})

    status = frame["数据状态"].astype(str).str.strip()
    if (status == "待填").any():
        issues.append({"类型": "仍有待填记录", "数量": int((status == "待填").sum())})
    return {
        "通过": not issues,
        "行数": len(frame),
        "股票数": int(frame["股票代码"].nunique()),
        "评分日期最早": frame["评分日期"].min().strftime("%Y-%m-%d") if frame["评分日期"].notna().any() else None,
        "评分日期最晚": frame["评分日期"].max().strftime("%Y-%m-%d") if frame["评分日期"].notna().any() else None,
        "问题": issues,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="数据模块/基本面历史快照.csv")
    args = parser.parse_args()
    result = audit(Path(args.path))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["通过"] else 1)


if __name__ == "__main__":
    main()
