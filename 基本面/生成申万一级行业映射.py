#!/usr/bin/env python3
"""为2014年以来申万历史分类生成到v3一级行业的保守映射。"""
import os
import pandas as pd

目录 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "历史数据")
一级 = {
    "11": "农林牧渔", "22": "基础化工", "23": "钢铁", "24": "有色金属", "27": "电子", "28": "汽车",
    "33": "家用电器", "34": "食品饮料", "35": "纺织服饰", "36": "轻工制造", "37": "医药生物",
    "41": "公用事业", "42": "交通运输", "43": "房地产", "45": "商贸零售", "46": "社会服务",
    "48": "银行", "49": "非银金融", "51": "综合", "61": "建筑材料", "62": "建筑装饰",
    "63": "电力设备", "64": "机械设备", "65": "国防军工", "71": "计算机", "72": "传媒",
    "73": "通信", "74": "煤炭", "75": "石油石化", "76": "环保", "77": "美容护理",
}
采掘细分 = {"210101": "石油石化", "210201": "煤炭", "210202": "煤炭", "210401": "石油石化", "210402": "石油石化"}

def 行业名称(code):
    code = str(code).zfill(6)
    return 采掘细分.get(code, 一级.get(code[:2]))

def main():
    raw_path = os.path.join(目录, "申万股票行业变动_raw.csv")
    raw = pd.read_csv(raw_path, dtype={"行业代码": str}, parse_dates=["生效日期"])
    codes = sorted(raw.loc[raw["生效日期"] >= pd.Timestamp("2014-01-01"), "行业代码"].unique())
    result = pd.DataFrame({"行业代码": codes})
    result["行业名称"] = result["行业代码"].map(行业名称)
    result["一级行业名称"] = result["行业名称"]
    result["分类版本"] = "申万2014/2021（按生效日）"
    result["来源"] = "申万行业分类标准；一级行业归并"
    result["核验备注"] = result["行业名称"].map(lambda x: "待人工核验" if pd.isna(x) else "一级行业归并")
    path = os.path.join(目录, "申万行业代码映射.csv")
    result.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"已生成 {len(result)} 个代码映射，其中 {result['行业名称'].notna().sum()} 个可归并，{result['行业名称'].isna().sum()} 个保留缺失: {path}")

if __name__ == "__main__":
    main()
