#!/usr/bin/env python3
"""将已核验的官方发布日期写入原始观测；未核验记录保持不可回测。"""
import os
import pandas as pd

目录=os.path.join(os.path.dirname(os.path.abspath(__file__)),"历史数据")
raw_path=os.path.join(目录,"公开宏观历史原始观测.csv")
check_path=os.path.join(目录,"公开指标发布日期核验.csv")
if not os.path.exists(check_path):
    raise SystemExit(f"缺少核验表：{check_path}；请从模板复制后填写官方发布日期和链接")
raw=pd.read_csv(raw_path,dtype=str)
check=pd.read_csv(check_path,dtype=str)
required={"指标键","统计期日期","官方发布日期","官方链接"}
if not required.issubset(check.columns): raise SystemExit("核验表字段不完整")
merged=raw.merge(check[list(required)],on=["指标键","统计期日期"],how="left")
ok=merged["官方发布日期"].notna() & merged["官方链接"].notna()
merged.loc[ok,"生效日期"]=merged.loc[ok,"官方发布日期"]
merged.loc[ok,"状态"]="发布日期已核验（官方页面）"
merged.to_csv(raw_path,index=False,encoding="utf-8-sig")
print(f"已核验并写入 {ok.sum()} 条官方发布日期；其余 {len(merged)-ok.sum()} 条仍不可回测")
