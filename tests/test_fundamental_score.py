import pandas as pd

from 基本面.计算个股评分 import 计算评分


def test_scores_are_ranked_and_missing_data_reduces_confidence():
    rows = []
    for code, roe, pe in [("600519", 0.30, 10), ("000001", 0.10, 30)]:
        rows.append({
            "股票代码": code, "行业名称": "食品", "实际披露日": "2026-04-01", "评分日期": "2026-05-01",
            "来源等级": "官方", "ROE": roe, "ROIC": roe, "FCF净利比": 1.2,
            "收入3年CAGR": 0.2, "扣非净利润3年CAGR": 0.2, "收入同比": 0.1,
            "扣非净利润同比": 0.1, "资产负债率": 0.4, "有息负债率": 0.2,
            "利息保障倍数": 8, "应收周转天数": 40, "存货周转天数": 50,
            "PE_TTM": pe, "PB_MRQ": 2, "EV_EBITDA": 8, "FCF_Yield": 0.05,
            "审计意见": "无保留意见", "监管处罚次数": 0, "大股东质押率": 0.0,
            "商誉净资产比": 0.1, "关联交易风险": "否",
        })
    rows[1]["ROIC"] = ""
    result = 计算评分(pd.DataFrame(rows), {"准入阈值": {"行业横截面最小样本数": 20}, "时效天数": {"季度财务": 180}})
    assert result.loc[0, "总分"] > result.loc[1, "总分"]
    assert result.loc[1, "置信度"] < result.loc[0, "置信度"]


def test_hard_risk_blocks_entry():
    row = {"股票代码": "600519", "实际披露日": "2026-04-01", "评分日期": "2026-05-01",
           "来源等级": "官方", "ROE": .2, "ROIC": .2, "FCF净利比": 1,
           "审计意见": "否定意见", "重大诉讼标记": "否", "关联交易风险": "否"}
    result = 计算评分(pd.DataFrame([row]), {"准入阈值": {}, "时效天数": {"季度财务": 180}})
    assert result.loc[0, "准入结论"] == "禁止新开仓"
