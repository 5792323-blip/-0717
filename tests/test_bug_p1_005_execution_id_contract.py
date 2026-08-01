"""BUG-P1-005A red tests for execution identity across attribution paths."""

import pandas as pd
import pytest

from 组合回测.统一多股执行器 import _写入股票归因过程, _股票归因


def _trade(execution_id="X1", **overrides):
    row = {
        "时间": "2025-01-02 09:31", "类型": "买入", "成交数量": 100,
        "总成本": 1001.0, "交易费用": 1.0, "order_id": "O1",
        "execution_id": execution_id,
    }
    row.update(overrides)
    return row


def _process():
    return pd.DataFrame([
        {"时间": "2025-01-02 09:31", "持仓市值": 1000.0},
        {"时间": "2025-01-03 09:31", "持仓市值": 1000.0},
    ])


def _assert_rejected_independently(trades):
    with pytest.raises((AssertionError, ValueError), match="execution|重复|唯一"):
        _股票归因(pd.DataFrame(trades), ending_value=1000)

    process = _process()
    before = process.copy(deep=True)
    with pytest.raises((AssertionError, ValueError), match="execution|重复|唯一"):
        _写入股票归因过程(process, pd.DataFrame(trades))
    pd.testing.assert_frame_equal(process, before)


def test_nonempty_duplicate_execution_id_is_rejected_by_both_paths():
    _assert_rejected_independently([_trade("X1"), _trade("X1")])


def test_nonadjacent_duplicate_execution_id_is_rejected_by_both_paths():
    _assert_rejected_independently([
        _trade("X1"), _trade("X2"), _trade("X1"),
    ])


def test_empty_execution_id_is_rejected_by_both_paths():
    _assert_rejected_independently([_trade(""), _trade("X2")])


def test_whitespace_execution_id_is_rejected_by_both_paths():
    _assert_rejected_independently([_trade("   "), _trade("X2")])


def test_none_execution_id_is_rejected_by_both_paths():
    _assert_rejected_independently([_trade(None), _trade("X2")])


def test_missing_execution_id_field_is_rejected_by_both_paths():
    first = _trade("X1")
    second = _trade("X2")
    del second["execution_id"]
    _assert_rejected_independently([first, second])


@pytest.mark.parametrize("raw_id", [1, 1.5])
def test_non_string_execution_id_type_is_rejected_by_both_paths(raw_id):
    _assert_rejected_independently([_trade(raw_id), _trade("X2")])


def test_one_valid_and_one_duplicate_execution_id_is_rejected_by_both_paths():
    _assert_rejected_independently([_trade("X1"), _trade("X2"), _trade("X1")])


def test_valid_same_order_id_with_distinct_execution_ids_is_preserved_by_both_paths():
    trades = pd.DataFrame([
        _trade("X1", 成交数量=40, 总成本=401.0),
        _trade("X2", 成交数量=60, 总成本=601.0, 时间="2025-01-02 09:32"),
    ])

    final = _股票归因(trades, ending_value=1000)
    process = _写入股票归因过程(
        pd.DataFrame([{"时间": "2025-01-02 09:32", "持仓市值": 1000.0}]),
        trades,
    )
    assert final["持仓数量"] == 100
    assert final["持仓成本"] == pytest.approx(1002.0)
    assert process.loc[0, "持仓成本"] == pytest.approx(final["持仓成本"])
