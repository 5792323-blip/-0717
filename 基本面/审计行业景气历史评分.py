#!/usr/bin/env python3
"""审计历史行业评分是否达到严格回测最低数据条件。"""
import json
import os
from datetime import datetime
import pandas as pd

目录=os.path.join(os.path.dirname(os.path.abspath(__file__)),"历史数据")
评分=os.path.join(目录,"行业景气评分历史.csv")
归属=os.path.join(目录,"股票行业归属历史.csv")
报告=os.path.join(目录,"行业景气历史评分质量审计.json")
scores=pd.read_csv(评分) if os.path.exists(评分) else pd.DataFrame()
industries=set(pd.read_csv(归属,usecols=["行业名称"])["行业名称"].dropna())
required={"行业名称","生效日期","行业景气指数","数据截止日","覆盖权重","来源","评分版本"}
issues=[]
if scores.empty: issues.append("行业评分历史为空")
elif not required.issubset(scores.columns): issues.append("行业评分历史字段不完整")
else:
    scores["生效日期"]=pd.to_datetime(scores["生效日期"],errors="coerce")
    scores["数据截止日"]=pd.to_datetime(scores["数据截止日"],errors="coerce")
    bad=scores["数据截止日"]>scores["生效日期"]
    if bad.any(): issues.append(f"存在{bad.sum()}条前视日期")
    low=pd.to_numeric(scores["覆盖权重"],errors="coerce")<.9
    if low.any(): issues.append(f"存在{low.sum()}条覆盖权重低于90%")
    missing=industries-set(scores["行业名称"].dropna())
    if missing: issues.append(f"缺少{len(missing)}个行业的任何评分")
result={"生成时间":datetime.now().isoformat(timespec="seconds"),"严格回测就绪":not issues,"评分记录数":len(scores),"覆盖行业数":int(scores["行业名称"].nunique()) if "行业名称" in scores else 0,"问题":issues}
with open(报告,"w",encoding="utf-8") as f: json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps(result,ensure_ascii=False,indent=2))
