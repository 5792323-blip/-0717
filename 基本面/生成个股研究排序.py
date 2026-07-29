#!/usr/bin/env python3
"""生成当前研究排序，并输出数据覆盖率审计。

研究排序只用于人工筛选，不会被历史准入过滤器读取。
"""

import argparse
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "基本面/个股评分结果.csv"
DEFAULT_OUTPUT = ROOT / "基本面/个股研究排序.csv"
DEFAULT_AUDIT = ROOT / "基本面/运行记录/个股覆盖率审计.json"


def 生成(frame):
    result = frame.copy()
    result["股票代码"] = result["股票代码"].astype(str).str.extract(r"(\d{6})", expand=False).fillna(result["股票代码"].astype(str).str.zfill(6))
    result["总分"] = pd.to_numeric(result["总分"], errors="coerce")
    result["置信度"] = pd.to_numeric(result["置信度"], errors="coerce")
    result["研究状态"] = result.apply(
        lambda row: "可优先研究" if row["置信度"] >= 0.40 and row["总分"] >= 65
        else "观察" if row["置信度"] >= 0.25 and row["总分"] >= 55
        else "数据不足",
        axis=1,
    )
    result = result.sort_values(["研究状态", "总分", "置信度"], ascending=[True, False, False])
    result.insert(0, "研究排名", range(1, len(result) + 1))
    columns = ["研究排名", "股票代码", "评分日期", "总分", "置信度", "研究状态", "评分状态", "准入结论"]
    return result[[column for column in columns if column in result.columns]]


def 审计(frame):
    metrics = [
        column for column in frame.columns
        if column.endswith("覆盖率")
    ]
    coverage = {}
    for column in metrics:
        values = pd.to_numeric(frame[column], errors="coerce")
        coverage[column] = {
            "平均覆盖率": round(float(values.mean()), 4) if values.notna().any() else 0.0,
            "完整覆盖数量": int((values >= 1).sum()),
            "低于50%数量": int((values < 0.5).sum()),
        }
    status = frame.get("准入结论", pd.Series(dtype=str)).astype(str).value_counts().to_dict()
    return {
        "评分行数": len(frame),
        "股票数": int(frame["股票代码"].nunique()),
        "评分日期": sorted(frame["评分日期"].dropna().astype(str).unique().tolist()),
        "准入结论分布": status,
        "维度覆盖率": coverage,
        "严格历史准入可用": bool((frame.get("置信度", pd.Series(dtype=float)).astype(float) >= 0.80).all()),
        "说明": "研究排序仅供当前人工筛选；严格历史准入仍需真实历史快照和行业历史评分。",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args()
    frame = pd.read_csv(args.input, dtype=str, keep_default_na=False)
    ranked = 生成(frame)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    ranked.to_csv(args.output, index=False, encoding="utf-8-sig")
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(json.dumps(审计(frame), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"输出": str(args.output), "审计": str(args.audit), "行数": len(ranked)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
