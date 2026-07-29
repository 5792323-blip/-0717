#!/usr/bin/env python3
"""审计个股基本面历史快照是否达到严格回测门槛。"""

import argparse
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "数据模块/基本面历史快照.csv"
DEFAULT_REPORT = ROOT / "基本面/运行记录/个股历史基本面审计.json"
REQUIRED_COLUMNS = [
    "股票代码", "实际披露日", "数据截止日", "评分日期", "数据来源", "数据状态",
    "ROE", "ROIC", "收入3年CAGR", "扣非净利润3年CAGR", "FCF净利比",
    "资产负债率", "有息负债率", "利息保障倍数", "PE_TTM", "PB_MRQ",
    "EV_EBITDA", "FCF_Yield", "审计意见", "监管处罚次数", "大股东质押率",
    "商誉净资产比", "关联交易风险",
]
CORE_NUMERIC = [
    "ROE", "ROIC", "收入3年CAGR", "扣非净利润3年CAGR", "FCF净利比",
    "资产负债率", "有息负债率", "利息保障倍数", "PE_TTM", "PB_MRQ",
    "EV_EBITDA", "FCF_Yield",
]


def 审计(frame, start_date="2020-01-01", end_date=None, min_stock_coverage=0.90):
    frame = frame.copy()
    issues = []
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        issues.append({"类型": "缺少字段", "字段": missing_columns})
    for column in ("实际披露日", "数据截止日", "评分日期"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
            invalid = int(frame[column].isna().sum())
            if invalid:
                issues.append({"类型": "日期无效", "字段": column, "数量": invalid})
    if {"实际披露日", "评分日期"}.issubset(frame.columns):
        future = frame[frame["实际披露日"] > frame["评分日期"]]
        if not future.empty:
            issues.append({"类型": "未来数据", "数量": len(future)})
    if {"数据截止日", "评分日期"}.issubset(frame.columns):
        future_cutoff = frame[frame["数据截止日"] > frame["评分日期"]]
        if not future_cutoff.empty:
            issues.append({"类型": "数据截止日晚于评分日", "数量": len(future_cutoff)})
    if {"股票代码", "评分日期"}.issubset(frame.columns):
        duplicate = frame.duplicated(["股票代码", "评分日期"], keep=False)
        if duplicate.any():
            issues.append({"类型": "股票评分日重复", "数量": int(duplicate.sum())})
    coverage = {}
    for column in CORE_NUMERIC:
        if column not in frame:
            coverage[column] = 0.0
            continue
        valid = pd.to_numeric(frame[column], errors="coerce").notna()
        coverage[column] = round(float(valid.mean()), 4) if len(frame) else 0.0
        if coverage[column] < min_stock_coverage:
            issues.append({"类型": "核心指标覆盖不足", "字段": column, "覆盖率": coverage[column]})
    stock_count = int(frame["股票代码"].nunique()) if "股票代码" in frame else 0
    score_dates = pd.to_datetime(frame["评分日期"], errors="coerce") if "评分日期" in frame else pd.Series(dtype="datetime64[ns]")
    in_range = score_dates[(score_dates >= pd.Timestamp(start_date)) & (score_dates <= pd.Timestamp(end_date or pd.Timestamp.today()))]
    distinct_dates = int(in_range.dt.normalize().nunique()) if not in_range.empty else 0
    if distinct_dates < 4:
        issues.append({"类型": "历史评分日期不足", "数量": distinct_dates, "最低要求": 4})
    if stock_count < 288:
        issues.append({"类型": "股票覆盖不足", "股票数": stock_count, "最低要求": 288})
    return {
        "通过": not issues,
        "行数": len(frame),
        "股票数": stock_count,
        "评分日期数": distinct_dates,
        "评分日期最早": in_range.min().strftime("%Y-%m-%d") if not in_range.empty else None,
        "评分日期最晚": in_range.max().strftime("%Y-%m-%d") if not in_range.empty else None,
        "核心指标覆盖率": coverage,
        "问题": issues,
        "说明": "通过后才允许基本面历史回测；当前快照不能复制到历史评分日。",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--start-date", default="2020-01-01")
    parser.add_argument("--end-date", default=None)
    args = parser.parse_args()
    frame = pd.read_csv(args.input, dtype=str, keep_default_na=False)
    result = 审计(frame, args.start_date, args.end_date)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["通过"] else 1)


if __name__ == "__main__":
    main()
