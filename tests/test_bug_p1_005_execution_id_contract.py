"""BUG-P1-005: execution identifiers must be unique across attribution paths."""

import pandas as pd
import pytest

from 组合回测.统一多股执行器 import _写入股票归因过程, _股票归因


def _trade(**overrides):
    row = {
        "时间": "2025-01-02 09:31", "类型": "买入", "成交数量": 100,
        "总成本": 1001.0, "交易费用": 1.0, "execution_id": "X1",
    }
    row.update(overrides)
    return row


def test_duplicate_execution_id_has_same_rejection_in_final_and_process_attribution():
    trades = pd.DataFrame([_trade(), _trade()])
    process = pd.DataFrame([
        {"时间": "2025-01-02", "持仓市值": 1000},
        {"时间": "2025-01-03", "持仓市值": 1000},
    ])

    with pytest.raises((AssertionError, ValueError), match="重复|execution"):
        _股票归因(trades, ending_value=1000)
    with pytest.raises((AssertionError, ValueError), match="重复|execution"):
        _写入股票归因过程(process, trades)
