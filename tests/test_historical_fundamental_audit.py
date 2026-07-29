import pandas as pd

from 基本面.审计个股历史基本面 import 审计


def _row(code, date):
    return {"股票代码": code, "实际披露日": date, "数据截止日": date, "评分日期": date,
            "数据来源": "test", "数据状态": "有效", "ROE": 1, "ROIC": 1,
            "收入3年CAGR": 1, "扣非净利润3年CAGR": 1, "FCF净利比": 1,
            "资产负债率": 1, "有息负债率": 1, "利息保障倍数": 1,
            "PE_TTM": 1, "PB_MRQ": 1, "EV_EBITDA": 1, "FCF_Yield": 1,
            "审计意见": "无保留意见", "监管处罚次数": 0, "大股东质押率": 0,
            "商誉净资产比": 0, "关联交易风险": "否"}


def test_historical_audit_passes_complete_multiple_dates():
    rows = [_row(f"{stock:06d}", f"202{period}-03-31") for stock in range(288) for period in range(4)]
    assert 审计(pd.DataFrame(rows))["通过"] is True


def test_historical_audit_rejects_current_single_snapshot():
    result = 审计(pd.DataFrame([_row("600519", "2026-07-28")]))
    assert result["通过"] is False
    assert any(item["类型"] == "历史评分日期不足" for item in result["问题"])
