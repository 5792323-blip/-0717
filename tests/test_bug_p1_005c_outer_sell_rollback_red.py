"""BUG-P1-005C red test for nested cross-executor sell rollback ownership."""

import pytest

from test_bug_p1_005c_approval_link_v2_support import (
    _buy,
    _sell,
    _trade_by_execution,
    executor_factory,
)


def test_red_outer_sell_recorder_failure_preserves_nested_buy_sell(
    executor_factory, monkeypatch
):
    account, executor_a = executor_factory(stock="600001")
    _, executor_b = executor_factory(account=account, stock="600002")
    assert _buy(executor_a, "600001") is True
    outer_position_before = executor_a.当前持仓["600001"]["股数"]
    initial_execution_id = executor_a.交易记录器.交易列表[-1]["execution_id"]
    executor_a._executor_marker = "outer"
    executor_b._executor_marker = "nested"

    recorder_a = executor_a.交易记录器
    recorder_b = executor_b.交易记录器
    lifecycle = {
        "outer_execution_id": None,
        "nested_buy_execution_id": None,
        "nested_sell_execution_id": None,
    }

    def fail_outer_after_nested_buy_sell(**kwargs):
        lifecycle["outer_execution_id"] = kwargs["execution_id"]
        assert _buy(executor_b, "600002") is True
        lifecycle["nested_buy_execution_id"] = recorder_b.交易列表[-1]["execution_id"]
        assert _sell(executor_b, "600002") is True
        lifecycle["nested_sell_execution_id"] = recorder_b.交易列表[-1]["execution_id"]
        raise RuntimeError("forced outer sell recorder failure")

    monkeypatch.setattr(recorder_a, "记录卖出", fail_outer_after_nested_buy_sell)
    with pytest.raises(RuntimeError, match="forced outer sell recorder failure"):
        _sell(executor_a, "600001")

    outer_execution_id = lifecycle["outer_execution_id"]
    nested_ids = {
        lifecycle["nested_buy_execution_id"],
        lifecycle["nested_sell_execution_id"],
    }
    assert isinstance(outer_execution_id, str) and outer_execution_id.strip()
    assert all(isinstance(execution_id, str) and execution_id.strip() for execution_id in nested_ids)
    assert outer_execution_id not in nested_ids

    trades_by_execution = _trade_by_execution((executor_a, executor_b))
    assert set(trades_by_execution) == {initial_execution_id, *nested_ids}
    assert [row["execution_id"] for row in recorder_a.交易列表] == [initial_execution_id]
    assert {row["execution_id"] for row in recorder_b.交易列表} == nested_ids
    assert executor_a._executor_marker == "outer"
    assert executor_b._executor_marker == "nested"

    assert executor_a.当前持仓["600001"]["股数"] == outer_position_before
    assert "600002" not in executor_b.当前持仓
    assert set(account.持仓) == {"600001"}
    assert account.持仓["600001"]["股数"] == outer_position_before

    scope = account._execution_scope
    assert outer_execution_id not in scope["execution_ids"]
    assert outer_execution_id not in scope["committed_execution_ids"]
    assert outer_execution_id not in scope["pending_execution_ids"]
    assert scope["execution_ids"] == {initial_execution_id, *nested_ids}
    assert scope["committed_execution_ids"] == {initial_execution_id, *nested_ids}
    assert scope["pending_execution_ids"] == {}
    approvals_by_execution = {
        row["execution_id"]: row
        for row in account.审批记录
        if row.get("execution_id")
    }
    assert set(approvals_by_execution) == {initial_execution_id, *nested_ids}
