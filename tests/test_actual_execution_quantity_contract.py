"""Actual execution quantity contract: reject invalid quantities."""

import pandas as pd
import pytest

from 组合回测.统一多股执行器 import _股票归因


def _trade(**overrides):
    row = {
        "时间": "2025-01-02 09:31", "类型": "买入", "成交数量": 100,
        "总成本": 1001.0, "交易费用": 1.0, "execution_id": "X1",
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize("quantity", [0, -1, float("nan"), None, "", "abc", 1.5])
def test_invalid_execution_quantity_is_rejected(quantity):
    trades = pd.DataFrame([_trade(**{"成交数量": quantity})])
    with pytest.raises((AssertionError, ValueError, TypeError), match="数量|成交"):
        _股票归因(trades, ending_value=1000)


@pytest.mark.parametrize("quantity", [1, 100, "100"])
def test_valid_execution_quantity_is_accepted(quantity):
    trades = pd.DataFrame([_trade(**{"成交数量": quantity})])
    result = _股票归因(trades, ending_value=1000)
    assert result["持仓数量"] == int(quantity)
