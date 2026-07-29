#!/usr/bin/env python3
"""缓存公开宏观历史原始观测；不把统计期日期误作评分生效日期。"""
import os
import pandas as pd
import akshare as ak

目录=os.path.join(os.path.dirname(os.path.abspath(__file__)),"历史数据")
序列={"综合|2-制造业PMI":"macro_china_pmi_yearly","银行|2-M2增速":"macro_china_m2_yearly"}
状态={"综合|2-制造业PMI":"发布日期已核验（国家统计局）","银行|2-M2增速":"不可用于回测：接口日期未核验为央行发布日期"}
rows=[]
for key, func in 序列.items():
    data=getattr(ak,func)().copy()
    data["原始数值"]=pd.to_numeric(data["今值"].astype(str).str.replace(",","",regex=False),errors="coerce")
    data=data.dropna(subset=["原始数值"])
    for _, row in data.iterrows():
        rows.append({"指标键":key,"统计期日期":str(row["日期"])[:10],"原始数值":row["原始数值"],"来源":f"AKShare/{func}","来源优先级":10,"生效日期":"","状态":状态[key]})
out=pd.DataFrame(rows).sort_values(["指标键","统计期日期"])
path=os.path.join(目录,"公开宏观历史原始观测.csv")
out.to_csv(path,index=False,encoding="utf-8-sig")
print(f"已缓存 {len(out)} 条原始观测（不可直接回测）: {path}")
