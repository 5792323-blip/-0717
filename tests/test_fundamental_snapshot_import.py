import pandas as pd
import pytest

from 基本面.导入个股基本面快照 import 标准化, 审计


def test_normalizes_and_derives_free_cash_flow():
    frame = 标准化(pd.DataFrame([{
        "代码": "SH_600519", "披露日期": "2026-04-30", "评分日期": "2026-05-01",
        "经营现金流净额": 120, "资本支出": 20, "归母净利润": 80,
    }]))
    assert frame.loc[0, "股票代码"] == "600519"
    assert frame.loc[0, "自由现金流"] == 100
    assert frame.loc[0, "FCF净利比"] == 1.25


def test_rejects_future_snapshot():
    frame = 标准化(pd.DataFrame([{
        "股票代码": "600519", "实际披露日": "2026-05-02", "评分日期": "2026-05-01",
    }]))
    result = 审计(frame)
    assert not result["通过"]
    assert any(item["类型"] == "未来数据" for item in result["问题"])


def test_requires_dates():
    with pytest.raises(ValueError, match="缺少必需字段"):
        标准化(pd.DataFrame([{"股票代码": "600519"}]))
