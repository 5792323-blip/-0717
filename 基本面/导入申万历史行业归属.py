#!/usr/bin/env python3
"""导入申万历史个股行业变动，并在行业代码完整映射后生成严格回测输入。"""

import argparse
import os

import pandas as pd


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
默认目录 = os.path.join(项目根目录, "基本面", "历史数据")


def _代码(value):
    return str(value).zfill(6)[-6:]


def 标准化原始数据(data):
    required = {"symbol", "start_date", "industry_code", "update_time"}
    if not required.issubset(data.columns):
        raise ValueError("申万原始数据缺少必要字段")
    result = data.loc[:, ["symbol", "start_date", "industry_code", "update_time"]].copy()
    result.columns = ["股票代码", "生效日期", "行业代码", "源更新日期"]
    result["股票代码"] = result["股票代码"].map(_代码)
    result["行业代码"] = result["行业代码"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    result["生效日期"] = pd.to_datetime(result["生效日期"], errors="coerce").dt.strftime("%Y-%m-%d")
    result["源更新日期"] = pd.to_datetime(result["源更新日期"], errors="coerce").dt.strftime("%Y-%m-%d")
    return result.dropna(subset=["股票代码", "生效日期", "行业代码"]).sort_values(["股票代码", "生效日期"])


def 生成行业归属(raw, mapping):
    required = {"行业代码", "行业名称"}
    if not required.issubset(mapping.columns):
        raise ValueError("行业代码映射缺少 行业代码、行业名称")
    mapping = mapping.loc[:, ["行业代码", "行业名称"]].copy()
    mapping["行业代码"] = mapping["行业代码"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    mapping["行业名称"] = mapping["行业名称"].fillna("").astype(str).str.strip()
    merged = raw.merge(mapping, on="行业代码", how="left", validate="many_to_one")
    missing = sorted(merged.loc[merged["行业名称"].isna() | (merged["行业名称"] == ""), "行业代码"].unique())
    result = merged.loc[~merged["行业名称"].isna() & (merged["行业名称"] != "")].copy()
    result = result.assign(分类标准="申万行业分类", 来源="申万宏源行业分类历史文件").loc[:, [
        "股票代码", "生效日期", "行业名称", "分类标准", "来源", "行业代码", "源更新日期",
    ]]
    return result, missing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--目录", default=默认目录)
    parser.add_argument("--代码映射", default="申万行业代码映射.csv")
    parser.add_argument("--起始生效日期", default="2014-01-01")
    args = parser.parse_args()
    directory = os.path.abspath(args.目录)
    os.makedirs(directory, exist_ok=True)

    import akshare as ak
    raw_full = 标准化原始数据(ak.stock_industry_clf_hist_sw())
    raw_path = os.path.join(directory, "申万股票行业变动_raw.csv")
    raw_full.to_csv(raw_path, index=False, encoding="utf-8-sig")
    raw = raw_full[pd.to_datetime(raw_full["生效日期"]) >= pd.Timestamp(args.起始生效日期)]

    mapping_path = args.代码映射 if os.path.isabs(args.代码映射) else os.path.join(directory, args.代码映射)
    if not os.path.isfile(mapping_path):
        pending = pd.DataFrame({"行业代码": sorted(raw["行业代码"].unique())})
        pending_path = os.path.join(directory, "申万行业代码映射待补清单.csv")
        pending.to_csv(pending_path, index=False, encoding="utf-8-sig")
        print(f"已保存原始行业变动 {len(raw_full):,} 条: {raw_path}")
        print(f"未找到代码映射；已生成待补清单 {len(pending):,} 个代码: {pending_path}")
        return

    mapped, missing = 生成行业归属(raw, pd.read_csv(mapping_path, dtype={"行业代码": str}))
    if missing:
        pending_path = os.path.join(directory, "申万行业代码映射待补清单.csv")
        pd.DataFrame({"行业代码": missing}).to_csv(pending_path, index=False, encoding="utf-8-sig")
    target = os.path.join(directory, "股票行业归属历史.csv")
    mapped.to_csv(target, index=False, encoding="utf-8-sig")
    print(f"已生成严格历史行业归属 {len(mapped):,} 条: {target}")
    if missing:
        print(f"仍缺 {len(missing):,} 个代码，相关股票会因历史归属缺失被拦截: {pending_path}")


if __name__ == "__main__":
    main()
