#!/usr/bin/env python3
"""审计 v3 工作簿当前台账，区分当前展示值和可用于严格回测的历史值。"""

import argparse
import json
from pathlib import Path

import pandas as pd


def 审计(workbook):
    frame = pd.read_excel(workbook, sheet_name="指标更新台账_v3")
    required = ["指标键", "行业", "当前值（原始）", "当前评分(1-10)", "数据发布日期", "数据状态", "建议权重", "角色"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        return {"通过": False, "问题": [{"类型": "缺少字段", "字段": missing}]}

    current_values = int(frame["当前值（原始）"].notna().sum())
    current_scores = int(frame["当前评分(1-10)"].notna().sum())
    published = pd.to_datetime(frame["数据发布日期"], errors="coerce")
    valid_dates = int(published.notna().sum())
    status = frame["数据状态"].fillna("").astype(str).str.strip()
    issues = []
    if valid_dates == 0:
        issues.append({"类型": "没有数据发布日期", "说明": "当前评分不能进入严格历史回测"})
    if (status == "待更新").all():
        issues.append({"类型": "全部指标待更新", "数量": len(frame)})
    if current_scores and valid_dates < current_scores:
        issues.append({"类型": "评分缺少发布日期", "数量": current_scores - valid_dates})

    by_industry = []
    for industry, group in frame.groupby("行业", dropna=False):
        weight = pd.to_numeric(group["建议权重"], errors="coerce").fillna(0)
        by_industry.append({
            "行业": str(industry),
            "指标数": int(len(group)),
            "当前值数": int(group["当前值（原始）"].notna().sum()),
            "当前评分数": int(group["当前评分(1-10)"].notna().sum()),
            "有发布日期数": int(pd.to_datetime(group["数据发布日期"], errors="coerce").notna().sum()),
            "建议权重合计": round(float(weight.sum()), 4),
        })
    return {
        "通过": not issues,
        "工作簿": str(workbook),
        "指标总数": len(frame),
        "行业数": int(frame["行业"].nunique()),
        "当前值数": current_values,
        "当前评分数": current_scores,
        "有发布日期数": valid_dates,
        "数据状态分布": status.value_counts().to_dict(),
        "问题": issues,
        "行业明细": sorted(by_industry, key=lambda item: item["行业"]),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", default="基本面/全行业景气度量化跟踪体系_v3_全行业核心驱动版.xlsx")
    parser.add_argument("--output", default="基本面/运行记录/v3当前台账审计.json")
    args = parser.parse_args()
    result = 审计(args.workbook)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "行业明细"}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["通过"] else 1)


if __name__ == "__main__":
    main()
