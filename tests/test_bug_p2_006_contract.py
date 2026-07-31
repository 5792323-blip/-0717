"""修复前契约：BUG-P2-006 成交事实边界与归因一致性。

这些断言刻意锁定应有的失败边界；本文件不修改生产代码，也不替时间
fallback 语义作业务裁决。时间来源观察测试只记录当前实现的可见结果。
"""

import math

import pandas as pd
import pytest

from 组合回测.统一多股执行器 import _写入股票归因过程, _股票归因
from 策略引擎.交易记录器 import 交易记录器


def _trade(**overrides):
    row = {
        "时间": "2025-01-02 09:31", "类型": "买入", "成交数量": 100,
        "总成本": 1001.0, "交易费用": 1.0, "execution_id": "X1",
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize("bad_time", [None, "", pd.NaT, "not-a-date"])
def test_actual_fill_with_invalid_time_is_rejected_before_ledger_write(bad_time):
    recorder = 交易记录器()
    recorder.记录本根K线(0, "2025-01-02", "09:31", 10, 10, 30, 30, 1)
    before = (len(recorder.交易列表), recorder.持仓记录[-1].copy())

    with pytest.raises((AssertionError, ValueError), match="时间|日期|成交"):
        recorder.记录买入(
            10, "test", 1, 1000, 10, 10, 成交数量=100,
            交易费用=1, 总成本=1001, 日期="", 时间=bad_time,
        )

    assert len(recorder.交易列表) == before[0]
    assert recorder.持仓记录[-1] == before[1]


@pytest.mark.parametrize(
    "fields, expected",
    [
        ({"时间": "2025-01-02"}, "2025-01-02"),
        ({"日期": "2025-01-02"}, "2025-01-02"),
        ({"时间": "2025-01-02", "日期": "2025-01-02"}, "2025-01-02"),
        ({"时间": "2025-01-03", "日期": "2025-01-02"}, None),
        ({}, None),
        ({"时间": "invalid", "日期": "also-invalid"}, None),
    ],
)
def test_trade_time_source_contract_is_explicit(fields, expected):
    # Observation contract: conflicting/missing/unparseable sources require
    # a product decision from C; they must not silently become a valid date.
    time_value = fields.get("时间", fields.get("日期"))
    parsed = pd.to_datetime(time_value, errors="coerce")
    observed = None if pd.isna(parsed) else str(parsed.date())
    if expected is None:
        assert observed is None or fields.get("时间") != fields.get("日期")
    else:
        assert observed == expected


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


def test_invalid_time_cannot_be_filtered_or_attributed_to_first_or_last_day():
    process = pd.DataFrame([
        {"时间": "2025-01-01", "持仓市值": 0},
        {"时间": "2025-01-03", "持仓市值": 1000},
    ])
    trades = pd.DataFrame([_trade(时间=None)])

    with pytest.raises((AssertionError, ValueError), match="时间|日期|成交"):
        _写入股票归因过程(process, trades)

