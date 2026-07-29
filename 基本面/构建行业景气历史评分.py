#!/usr/bin/env python3
"""由带发布日期的指标评分构建可用于严格回测的行业景气历史表。"""
import argparse
import os
import pandas as pd

根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
一级行业 = {"农林牧渔","基础化工","钢铁","有色金属","电子","汽车","家用电器","食品饮料","纺织服饰","轻工制造","医药生物","公用事业","交通运输","房地产","商贸零售","社会服务","综合","建筑材料","建筑装饰","电力设备","机械设备","国防军工","计算机","传媒","通信","银行","非银金融","煤炭","石油石化","环保","美容护理"}

def 构建(ledger, history, min_coverage=0.9):
    weights = ledger.loc[ledger["行业"].isin(一级行业), ["指标键", "行业", "建议权重"]].copy()
    weights["建议权重"] = pd.to_numeric(weights["建议权重"], errors="coerce")
    history = history.copy()
    if "来源优先级" not in history:
        history["来源优先级"] = 10
    history["来源优先级"] = pd.to_numeric(history["来源优先级"], errors="coerce").fillna(10)
    data = history.merge(weights, on="指标键", how="inner", validate="many_to_one")
    data["生效日期"] = pd.to_datetime(data["生效日期"], errors="coerce").dt.normalize()
    data["数据截止日"] = pd.to_datetime(data["数据截止日"], errors="coerce").dt.normalize()
    data["指标评分"] = pd.to_numeric(data["指标评分"], errors="coerce")
    data = data.dropna(subset=["生效日期","数据截止日","指标评分","建议权重"])
    data = data[data["数据截止日"] <= data["生效日期"]]
    # 同一指标同一时点，确认数据可用更高优先级覆盖公开初版。
    data = data.sort_values(["指标键", "生效日期", "来源优先级", "数据截止日"]).drop_duplicates(
        ["指标键", "生效日期"], keep="last"
    )
    rows=[]
    for (date, industry), group in data.groupby(["生效日期","行业"]):
        available = group["建议权重"].sum()
        total = weights.loc[weights["行业"] == industry, "建议权重"].sum()
        coverage = available / total if total else 0
        if coverage < min_coverage: continue
        score = (group["指标评分"] * group["建议权重"]).sum() / available
        rows.append({"行业名称":industry,"生效日期":date.strftime("%Y-%m-%d"),"行业景气指数":round(score,4),"数据截止日":group["数据截止日"].max().strftime("%Y-%m-%d"),"覆盖权重":round(coverage,4),"来源":"v3指标更新台账历史评分","评分版本":"v3","备注":"仅使用当时已披露指标"})
    columns=["行业名称","生效日期","行业景气指数","数据截止日","覆盖权重","来源","评分版本","备注"]
    return pd.DataFrame(rows, columns=columns)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--工作簿",default=os.path.join(根目录,"基本面","全行业景气度量化跟踪体系_v3_全行业核心驱动版.xlsx")); parser.add_argument("--输入",default=os.path.join(根目录,"基本面","历史数据","行业指标评分历史.csv")); parser.add_argument("--输出",default=os.path.join(根目录,"基本面","历史数据","行业景气评分历史.csv")); parser.add_argument("--最低覆盖权重",type=float,default=.9); args=parser.parse_args()
    ledger=pd.read_excel(args.工作簿,sheet_name="指标更新台账_v3")
    result=构建(ledger,pd.read_csv(args.输入),args.最低覆盖权重)
    result.to_csv(args.输出,index=False,encoding="utf-8-sig"); print(f"已生成 {len(result)} 条行业评分: {args.输出}")
if __name__=="__main__": main()
