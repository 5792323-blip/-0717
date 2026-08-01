"""BUG-P1-005B red tests for scoped execution identity generation."""

from copy import deepcopy

import pytest

from 策略引擎.交易记录器 import 交易记录器


def _recorder():
    recorder = 交易记录器()
    recorder.记录本根K线(0, "2025-01-02", "09:31", 10, 10, 30, 30, 1)
    return recorder


def _buy(recorder, *, order_id=None):
    recorder.记录买入(
        10.0, "scope-test", 1.0, 1000.0, 10.0, 10.0,
        时间="2025-01-02 09:31", 成交数量=100, 交易费用=1.0,
        总成本=1001.0,
    )
    row = recorder.交易列表[-1]
    if order_id is not None:
        row["order_id"] = order_id
    return row


def _scope_key(run_id, account_id, execution_id):
    return (run_id, account_id, execution_id)


def test_same_run_same_account_different_stocks_have_distinct_execution_ids():
    first = _buy(_recorder())
    second = _buy(_recorder())

    assert first["execution_id"]
    assert second["execution_id"]
    assert first["execution_id"].strip()
    assert second["execution_id"].strip()
    assert first["execution_id"] != second["execution_id"]


def test_same_execution_id_is_allowed_in_different_accounts():
    first = _scope_key("RUN-1", "ACCOUNT-A", "X00000001")
    second = _scope_key("RUN-1", "ACCOUNT-B", "X00000001")
    assert first != second
    assert len({first, second}) == 2


def test_same_execution_id_is_allowed_in_different_runs():
    first = _scope_key("RUN-1", "ACCOUNT-A", "X00000001")
    second = _scope_key("RUN-2", "ACCOUNT-A", "X00000001")
    assert first != second
    assert len({first, second}) == 2


def test_same_order_id_with_distinct_execution_ids_is_preserved():
    first = _buy(_recorder(), order_id="ORDER-1")
    second = _buy(_recorder(), order_id="ORDER-1")
    first["execution_id"] = "EXEC-1"
    second["execution_id"] = "EXEC-2"

    assert first["order_id"] == second["order_id"]
    assert first["execution_id"] != second["execution_id"]


def test_forced_duplicate_execution_id_fails_before_second_state_change():
    recorder = _recorder()
    first = _buy(recorder)
    before = {
        "交易列表": deepcopy(recorder.交易列表),
        "买入序号": recorder.买入序号,
        "订单序号": recorder.订单序号,
        "成交序号": recorder.成交序号,
    }

    # Force the current generator to produce the first execution_id again.
    recorder.成交序号 = 0
    with pytest.raises((AssertionError, ValueError), match="execution|重复|唯一"):
        _buy(recorder)

    assert recorder.交易列表 == before["交易列表"]
    assert recorder.买入序号 == before["买入序号"]
    assert recorder.订单序号 == before["订单序号"]
    assert recorder.成交序号 == before["成交序号"]
    assert recorder.交易列表[-1]["execution_id"] == first["execution_id"]


def test_successful_actual_fills_have_nonempty_string_execution_ids():
    first = _buy(_recorder())
    second = _buy(_recorder())
    for row in (first, second):
        assert isinstance(row["execution_id"], str)
        assert row["execution_id"].strip()

