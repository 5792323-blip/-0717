#!/usr/bin/env python3
"""审计行业景气P0历史指标的数据源可得性，不将来源可见性误作历史数据已补齐。"""
import os
import pandas as pd

根目录=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
输入=os.path.join(根目录,"基本面","历史数据","行业历史指标采集清单.csv")
输出=os.path.join(根目录,"基本面","历史数据","行业历史数据源就绪审计.csv")
公开机关=("国家统计局","央行","海关总署","工信部","财政部","发改委","国家能源局","农业农村部","国家医保局","国家新闻出版署","商务部","交易所")
需授权=("Wind","Choice","iFinD","QuestMobile","Mysteel","SMM","卓创","中指院","波罗的海","小松","应用材料","ASML","AWS","Azure","阿里云","携程","去哪儿","木材指数","数字水泥","日本机床")

data=pd.read_csv(输入)
data=data[data["历史优先级"]=="P0"].copy()
def classify(source):
    if any(x in source for x in 需授权): return "第三方/公司数据：需授权或人工导入"
    if any(x in source for x in 公开机关): return "公开官方源：待开发历史抓取与时点校验"
    return "来源待核验"
data["数据源就绪状态"]=data["数据来源"].fillna("").map(classify)
data["当前可用于回测"]="否：尚未导入带生效日期的历史观测"
data.to_csv(输出,index=False,encoding="utf-8-sig")
print(data["数据源就绪状态"].value_counts().to_string())
print(f"已生成 {len(data)} 项P0数据源审计: {输出}")
