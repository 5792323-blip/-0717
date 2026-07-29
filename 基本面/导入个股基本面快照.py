#!/usr/bin/env python3
"""导入并合并个股基本面历史快照。

输入可以是研究终端或公开数据接口导出的 CSV。脚本不下载和猜测数据，
只负责字段标准化、衍生指标计算、按披露日去重和安全合并。
"""

import argparse
import json
from pathlib import Path

import pandas as pd


ALIASES = {
    "股票代码": ["股票代码", "代码", "证券代码", "stock_code"],
    "公司名称": ["公司名称", "股票简称", "名称", "name"],
    "行业名称": ["行业名称", "所属行业", "行业", "industry"],
    "报告期": ["报告期", "报告期末", "截止日期", "period"],
    "实际披露日": ["实际披露日", "公告日期", "披露日期", "公告日", "available_date"],
    "数据截止日": ["数据截止日", "数据日期", "截止日", "data_date"],
    "数据来源": ["数据来源", "来源", "source"],
    "来源等级": ["来源等级", "来源优先级", "source_level"],
    "收入": ["收入", "营业收入", "营业总收入", "revenue"],
    "归母净利润": ["归母净利润", "净利润", "归属于母公司股东的净利润", "net_profit"],
    "扣非净利润": ["扣非净利润", "扣非归母净利润", "net_profit_deducted"],
    "经营现金流净额": ["经营现金流净额", "经营活动产生的现金流量净额", "cfo"],
    "资本支出": ["资本支出", "购建固定资产无形资产和其他长期资产支付的现金", "capex"],
    "ROE": ["ROE", "净资产收益率", "roe"],
    "ROIC": ["ROIC", "投入资本回报率", "roic"],
    "毛利率": ["毛利率", "gross_margin"],
    "净利率": ["净利率", "net_margin"],
    "资产负债率": ["资产负债率", "debt_ratio"],
    "有息负债率": ["有息负债率", "interest_bearing_debt_ratio"],
    "利息保障倍数": ["利息保障倍数", "interest_coverage"],
    "应收周转天数": ["应收周转天数", "receivable_days"],
    "存货周转天数": ["存货周转天数", "inventory_days"],
    "PE_TTM": ["PE_TTM", "PE(TTM)", "市盈率TTM", "pe_ttm"],
    "PB_MRQ": ["PB_MRQ", "PB(MRQ)", "市净率", "pb_mrq"],
    "EV_EBITDA": ["EV_EBITDA", "EV/EBITDA", "ev_ebitda"],
    "FCF_Yield": ["FCF_Yield", "自由现金流收益率", "fcf_yield"],
    "审计意见": ["审计意见", "审计报告意见", "audit_opinion"],
    "监管处罚次数": ["监管处罚次数", "处罚次数", "penalty_count"],
    "重大诉讼标记": ["重大诉讼标记", "重大诉讼", "major_litigation"],
    "大股东质押率": ["大股东质押率", "质押率", "pledge_ratio"],
    "商誉净资产比": ["商誉净资产比", "商誉/净资产", "goodwill_to_equity"],
    "关联交易风险": ["关联交易风险", "related_party_risk"],
}

NUMERIC = [
    "收入", "归母净利润", "扣非净利润", "经营现金流净额", "资本支出", "ROE", "ROIC",
    "毛利率", "净利率", "资产负债率", "有息负债率", "利息保障倍数", "应收周转天数",
    "存货周转天数", "PE_TTM", "PB_MRQ", "EV_EBITDA", "FCF_Yield", "监管处罚次数",
    "大股东质押率", "商誉净资产比",
]


def _rename(frame):
    rename = {}
    for target, aliases in ALIASES.items():
        source = next((item for item in aliases if item in frame.columns), None)
        if source:
            rename[source] = target
    return frame.rename(columns=rename).copy()


def 标准化(frame, source="手工导入"):
    frame = _rename(frame)
    required = ["股票代码", "实际披露日", "评分日期"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"缺少必需字段: {', '.join(missing)}")
    frame["股票代码"] = frame["股票代码"].astype(str).str.extract(r"(\d{6})", expand=False)
    for column in ("实际披露日", "数据截止日", "评分日期"):
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce").dt.strftime("%Y-%m-%d")
    for column in NUMERIC:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "数据来源" not in frame.columns:
        frame["数据来源"] = source
    frame["数据状态"] = frame.get("数据状态", "有效").replace("", "有效")
    if "资本支出" in frame.columns and "经营现金流净额" in frame.columns:
        frame["自由现金流"] = frame["经营现金流净额"] - frame["资本支出"].fillna(0)
    if "自由现金流" in frame.columns and "归母净利润" in frame.columns:
        denominator = frame["归母净利润"].replace(0, pd.NA)
        frame["FCF净利比"] = frame["自由现金流"] / denominator
    return frame.dropna(subset=["股票代码", "实际披露日", "评分日期"])


def 合并快照(existing, incoming):
    all_columns = list(dict.fromkeys([*existing.columns, *incoming.columns]))
    combined = pd.concat([existing.reindex(columns=all_columns), incoming.reindex(columns=all_columns)], ignore_index=True)
    combined["实际披露日"] = pd.to_datetime(combined["实际披露日"], errors="coerce")
    combined = combined.sort_values(["股票代码", "实际披露日", "评分日期"])
    return combined.drop_duplicates(["股票代码", "实际披露日"], keep="last").sort_values(["股票代码", "实际披露日"])


def 审计(frame):
    issues = []
    for column in ("实际披露日", "评分日期"):
        dates = pd.to_datetime(frame[column], errors="coerce")
        if dates.isna().any():
            issues.append({"类型": "日期无效", "字段": column, "数量": int(dates.isna().sum())})
    disclosure = pd.to_datetime(frame["实际披露日"], errors="coerce")
    score_date = pd.to_datetime(frame["评分日期"], errors="coerce")
    future = disclosure > score_date
    if future.any():
        issues.append({"类型": "未来数据", "数量": int(future.sum())})
    duplicate = frame.duplicated(["股票代码", "实际披露日"], keep=False)
    if duplicate.any():
        issues.append({"类型": "重复快照", "数量": int(duplicate.sum())})
    return {"通过": not issues, "行数": len(frame), "股票数": int(frame["股票代码"].nunique()), "问题": issues}


def main():
    parser = argparse.ArgumentParser(description="导入个股基本面历史快照")
    parser.add_argument("input", help="研究终端导出的 CSV")
    parser.add_argument("--output", default="数据模块/基本面历史快照.csv")
    parser.add_argument("--source", default="手工导入")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    incoming = 标准化(pd.read_csv(args.input), args.source)
    output = Path(args.output)
    existing = pd.read_csv(output, dtype=str) if output.exists() else pd.DataFrame(columns=incoming.columns)
    if not existing.empty:
        existing = 标准化(existing, args.source)
    merged = 合并快照(existing, incoming)
    result = 审计(merged)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["通过"]:
        raise SystemExit(1)
    if not args.check_only:
        output.parent.mkdir(parents=True, exist_ok=True)
        merged["实际披露日"] = merged["实际披露日"].dt.strftime("%Y-%m-%d")
        merged.to_csv(output, index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
