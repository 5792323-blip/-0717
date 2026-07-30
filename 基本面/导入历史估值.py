#!/usr/bin/env python3
"""安全合并外部历史估值；只按股票代码和实际披露日填补缺失值。"""

import argparse
import json
from pathlib import Path

import pandas as pd


FIELDS = ["PE_TTM", "PB_MRQ", "EV_EBITDA", "FCF_Yield"]
KEYS = ["股票代码", "实际披露日"]


def 合并历史估值(base_path, valuation_path, output_path, check_only=False):
    base = pd.read_csv(base_path, dtype=str, keep_default_na=False)
    incoming = pd.read_csv(valuation_path, dtype=str, keep_default_na=False)
    missing = [c for c in KEYS + FIELDS[:2] if c not in incoming.columns]
    if missing:
        raise ValueError(f"估值文件缺少字段: {', '.join(missing)}")
    # 不同公开估值源覆盖范围不同；缺失的可选字段保持为空。
    for field in FIELDS[2:]:
        if field not in incoming.columns:
            incoming[field] = ""
    for frame in (base, incoming):
        frame["股票代码"] = frame["股票代码"].astype(str).str.extract(r"(\d{6})", expand=False)
        frame["实际披露日"] = pd.to_datetime(frame["实际披露日"], errors="coerce")
        if "评分日期" in frame:
            frame["评分日期"] = pd.to_datetime(frame["评分日期"], errors="coerce")
    incoming = incoming.dropna(subset=KEYS).copy()
    if "评分日期" in incoming.columns:
        invalid = incoming[incoming["实际披露日"] > incoming["评分日期"]]
        if not invalid.empty:
            raise ValueError(f"估值文件存在未来数据: {len(invalid)} 条")
    incoming = incoming.drop_duplicates(KEYS, keep="last")
    base_index = pd.MultiIndex.from_frame(base[KEYS])
    incoming = incoming.set_index(KEYS)
    filled = 0
    for field in FIELDS:
        values = pd.to_numeric(incoming[field], errors="coerce")
        for idx, value in values.items():
            if idx not in base_index or pd.isna(value):
                continue
            row = base_index.get_loc(idx)
            positions = [row] if isinstance(row, int) else list(row)
            for position in positions:
                if str(base.at[position, field]).strip() == "":
                    base.at[position, field] = value
                    filled += 1
    # 日频估值通常不会恰好落在财报披露日；对仍缺失的 PE/PB，
    # 使用同一股票在披露日前最近一个交易日的值，严格禁止未来值。
    asof_fields = [field for field in FIELDS[:2] if field in incoming.columns]
    if asof_fields:
        source = incoming.reset_index()
        for position, row in base.iterrows():
            if pd.isna(row["实际披露日"]):
                continue
            candidates = source[
                (source["股票代码"] == row["股票代码"])
                & (source["实际披露日"] <= row["实际披露日"])
            ].sort_values("实际披露日")
            if candidates.empty:
                continue
            latest = candidates.iloc[-1]
            for field in asof_fields:
                if str(row[field]).strip() != "":
                    continue
                value = pd.to_numeric(latest[field], errors="coerce")
                if pd.notna(value):
                    base.at[position, field] = value
                    filled += 1
    report = {"基础文件": str(base_path), "估值文件": str(valuation_path), "填补单元格数": filled,
              "输入估值记录数": len(incoming), "仅检查": check_only}
    if not check_only:
        base["实际披露日"] = base["实际披露日"].dt.strftime("%Y-%m-%d")
        if "评分日期" in base:
            base["评分日期"] = base["评分日期"].dt.strftime("%Y-%m-%d")
        base.to_csv(output_path, index=False, encoding="utf-8-sig")
        report["输出"] = str(output_path)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("valuation", help="外部历史估值 CSV")
    parser.add_argument("--base", default="数据模块/基本面历史快照_2020_2026.csv")
    parser.add_argument("--output", default="数据模块/基本面历史快照_2020_2026.csv")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(合并历史估值(Path(args.base), Path(args.valuation), Path(args.output), args.check_only), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
