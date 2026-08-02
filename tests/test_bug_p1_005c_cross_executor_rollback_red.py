"""BUG-P1-005C red test for nested cross-executor transaction ownership."""

import pytest

from test_bug_p1_005c_approval_link_v2_support import (
    _buy,
    _trade_by_execution,
    executor_factory,
)


def test_red_cross_executor_nested_commit_preserves_state_ownership(
    executor_factory, monkeypatch
):
    account, executor_a = executor_factory(stock="600001")
    _, executor_b = executor_factory(account=account, stock="600002")
    executor_a._cross_executor_state_marker = "executor-a"
    executor_b._cross_executor_state_marker = "executor-b"

    recorder_a = executor_a.交易记录器
    recorder_b = executor_b.交易记录器
    original_record_buy_b = recorder_b.记录买入
    lifecycle = {"outer_execution_id": None, "nested_execution_id": None}

    def capture_nested_buy(**kwargs):
        lifecycle["nested_execution_id"] = kwargs["execution_id"]
        return original_record_buy_b(**kwargs)

    def fail_outer_after_nested_buy(**kwargs):
        lifecycle["outer_execution_id"] = kwargs["execution_id"]
        assert _buy(executor_b, "600002")
        raise RuntimeError("forced outer executor failure")

    monkeypatch.setattr(recorder_a, "记录买入", fail_outer_after_nested_buy)
    monkeypatch.setattr(recorder_b, "记录买入", capture_nested_buy)
    with pytest.raises(RuntimeError, match="forced outer executor failure"):
        _buy(executor_a, "600001")

    outer_execution_id = lifecycle["outer_execution_id"]
    nested_execution_id = lifecycle["nested_execution_id"]
    assert isinstance(outer_execution_id, str) and outer_execution_id.strip()
    assert isinstance(nested_execution_id, str) and nested_execution_id.strip()
    assert nested_execution_id != outer_execution_id

    trades_by_execution = _trade_by_execution((executor_a, executor_b))
    assert set(trades_by_execution) == {nested_execution_id}
    assert executor_a.交易记录器.交易列表 == []
    assert {
        trade["execution_id"] for trade in executor_b.交易记录器.交易列表
    } == {nested_execution_id}

    assert executor_a._cross_executor_state_marker == "executor-a"
    assert executor_b._cross_executor_state_marker == "executor-b"

    scope = account._execution_scope
    assert outer_execution_id not in scope["execution_ids"]
    assert outer_execution_id not in scope["committed_execution_ids"]
    assert outer_execution_id not in scope["pending_execution_ids"]
    assert scope["execution_ids"] == {nested_execution_id}
    assert scope["committed_execution_ids"] == {nested_execution_id}
    assert scope["pending_execution_ids"] == {}

    assert set(account.持仓) == {"600002"}
    assert account.持仓["600002"]["股数"] == trades_by_execution[nested_execution_id]["成交数量"]
    approvals_by_execution = {
        row["execution_id"]: row
        for row in account.审批记录
        if row.get("execution_id")
    }
    assert set(approvals_by_execution) == {nested_execution_id}
