"""Agent D audit tests for accounting and execution-fact invariants.

These tests intentionally exercise the narrow accounting contracts directly;
they do not change production behavior or silently normalize invalid facts.
"""

import pandas as pd
import pytest

from 策略引擎.交易账户 import 交易账户
from 组合回测.统一多股执行器 import _股票归因


def test_rejected_approval_cannot_change_cash_or_position():
    account = 交易账户(10_000)
    view = account.股票视图("600001")
    before = account.快照()

    view.记录审批(
        类型="买入", 结果="组合层拦截", 原因="现金不足",
        请求股数=100, 成交股数=0, 成交价=100, 交易费用=10,
    )

    after = account.快照()
    assert after["现金"] == pytest.approx(before["现金"])
    assert after["持仓市值"] == pytest.approx(before["持仓市值"])
    assert after["权益"] == pytest.approx(before["权益"])
    assert account.持仓 == {}


def test_zero_trade_stock_has_zero_contribution_even_if_external_value_is_present():
    empty = pd.DataFrame(columns=["时间", "类型", "成交数量"])
    result = _股票归因(empty, ending_value=1_000.0)

    # A stock with no actual execution cannot inherit portfolio value/PnL.
    assert result["持仓数量"] == 0
    assert result["已实现损益"] == pytest.approx(0.0)
    assert result["未实现损益"] == pytest.approx(0.0)
    assert result["累计损益贡献"] == pytest.approx(0.0)


def test_trade_ledger_rejects_duplicate_execution_id():
    trades = pd.DataFrame([
        {
            "时间": "2025-01-02", "execution_id": "X1", "类型": "买入",
            "成交数量": 100, "总成本": 1_001,
        },
        {
            "时间": "2025-01-02", "execution_id": "X1", "类型": "买入",
            "成交数量": 100, "总成本": 1_001,
        },
    ])

    with pytest.raises((AssertionError, ValueError), match="重复|duplicate|execution"):
        _股票归因(trades, ending_value=2_000)
