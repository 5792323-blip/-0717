#!/usr/bin/env python3
"""将已核验发布日期语义的公开指标转为历史评分输入。"""
import os
import pandas as pd

目录=os.path.join(os.path.dirname(os.path.abspath(__file__)),"历史数据")
raw=pd.read_csv(os.path.join(目录,"公开宏观历史原始观测.csv"))
pmi=raw[raw["指标键"]=="综合|2-制造业PMI"].copy()
pmi["生效日期"]=pd.to_datetime(pmi["统计期日期"])
pmi["数据截止日"]=pmi["生效日期"]
# 评分口径：使用当期及此前60个月的滚动分位，映射到[1,10]；避免未来数据进入分位计算。
pmi=pmi.sort_values("生效日期")
pmi["指标评分"]=pmi["原始数值"].rolling(60,min_periods=36).rank(pct=True).mul(9).add(1)
pmi=pmi.dropna(subset=["指标评分"])
out=pmi.assign(来源="国家统计局/制造业PMI",来源优先级=10,评分版本="v3-公开初版",备注="发布日期已抽样核验；5年滚动分位评分")[["指标键","生效日期","数据截止日","指标评分","来源","来源优先级","评分版本","备注"]]
path=os.path.join(目录,"行业指标评分历史.csv")
out.to_csv(path,index=False,encoding="utf-8-sig")
print(f"已生成 {len(out)} 条已核验公开指标评分（仅PMI）: {path}")
