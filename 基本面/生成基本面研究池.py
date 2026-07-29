#!/usr/bin/env python3
"""按硬风险、覆盖率和评分生成当前基本面研究池。

输出仅供人工研究和小样本对照回测，不会被交易过滤器读取。
"""

import argparse
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCORE = ROOT / "基本面/个股评分结果.csv"
SNAPSHOT = ROOT / "数据模块/基本面历史快照.csv"
OUTPUT = ROOT / "基本面/基本面研究池.csv"
REPORT = ROOT / "基本面/运行记录/基本面研究池报告.json"


def _number(row, column):
    value = pd.to_numeric(row.get(column), errors="coerce")
    return None if pd.isna(value) else float(value)


def _risk_reasons(row):
    reasons = []
    raw = str(row.get("硬风险", "")).strip()
    if raw and raw.lower() not in ("nan", "none"):
        reasons.extend(item for item in raw.replace("，", "、").split("、") if item)
    audit = str(row.get("审计意见", "")).strip()
    if audit in ("否定意见", "无法表示意见"):
        reasons.append(audit)
    litigation = str(row.get("重大诉讼标记", "")).strip()
    if litigation in ("立案未结", "是"):
        reasons.append("重大诉讼")
    related = str(row.get("关联交易风险", "")).strip()
    if related in ("重大资金占用", "是"):
        reasons.append("重大资金占用")
    return list(dict.fromkeys(reasons))


def _review_reasons(row):
    reasons = []
    roe, roic = _number(row, "ROE"), _number(row, "ROIC")
    if roe is not None and roic is not None and roe < 0 and roic < 0:
        reasons.append("ROE与ROIC同时为负，需复核连续性")
    profit, cashflow = _number(row, "归母净利润"), _number(row, "经营现金流净额")
    if profit is not None and cashflow is not None and profit > 0 and cashflow < 0:
        reasons.append("盈利为正但经营现金流为负，需复核连续性")
    return reasons


def 生成(score, snapshot, limit=50):
    score = score.copy()
    snapshot = snapshot.copy()
    score["股票代码"] = score["股票代码"].astype(str).str.extract(r"(\d{6})", expand=False)
    snapshot["股票代码"] = snapshot["股票代码"].astype(str).str.extract(r"(\d{6})", expand=False)
    raw_columns = ["股票代码", "审计意见", "重大诉讼标记", "关联交易风险", "ROE", "ROIC", "归母净利润", "经营现金流净额"]
    merged = score.merge(snapshot[[c for c in raw_columns if c in snapshot.columns]], on="股票代码", how="left")
    merged["总分"] = pd.to_numeric(merged["总分"], errors="coerce")
    merged["置信度"] = pd.to_numeric(merged["置信度"], errors="coerce")
    merged["硬筛选原因"] = merged.apply(lambda row: "、".join(_risk_reasons(row)), axis=1)
    merged["复核提醒"] = merged.apply(lambda row: "、".join(_review_reasons(row)), axis=1)
    merged["研究分层"] = merged.apply(
        lambda row: "硬风险排除" if row["硬筛选原因"] else
        "可优先研究" if row["总分"] >= 70 and row["置信度"] >= 0.40 else
        "观察" if row["总分"] >= 60 and row["置信度"] >= 0.25 else
        "数据不足", axis=1)
    merged["入选研究池"] = False
    candidates = merged[merged["研究分层"].isin(["可优先研究", "观察"])].sort_values(
        ["研究分层", "总分", "置信度"], ascending=[True, False, False]
    )
    merged.loc[candidates.head(limit).index, "入选研究池"] = True
    merged = merged.sort_values(["入选研究池", "研究分层", "总分", "置信度"], ascending=[False, True, False, False])
    merged.insert(0, "研究排名", range(1, len(merged) + 1))
    columns = ["研究排名", "股票代码", "评分日期", "总分", "置信度", "研究分层", "入选研究池", "硬筛选原因", "复核提醒", "准入结论"]
    return merged[[c for c in columns if c in merged.columns]]


def 报告(pool):
    return {
        "股票数": len(pool),
        "研究分层分布": pool["研究分层"].value_counts().to_dict(),
        "研究池数量": int(pool["入选研究池"].sum()),
        "研究池上限": 50,
        "严格历史准入": False,
        "说明": "明确事件风险才硬排除；单期财务异常仅作为复核提醒。研究池不拦截正式回测交易。",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--score", type=Path, default=SCORE)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    score = pd.read_csv(args.score, dtype=str, keep_default_na=False)
    snapshot = pd.read_csv(args.snapshot, dtype=str, keep_default_na=False)
    pool = 生成(score, snapshot, args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pool.to_csv(args.output, index=False, encoding="utf-8-sig")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(报告(pool), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"输出": str(args.output), "报告": str(args.report), **报告(pool)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
