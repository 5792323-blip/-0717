"""BUG-P1-005C red test for nested same-executor transaction ownership."""

import pytest

from test_bug_p1_005c_approval_link_v2_support import (
    _buy,
    _trade_by_execution,
    executor_factory,
)


def test_red_nested_same_executor_commit_survives_outer_recorder_failure(
    executor_factory, monkeypatch
):
    account, executor = executor_factory(stock="600001")
    recorder = executor.交易记录器
    original_record_buy = recorder.记录买入
    lifecycle = {"depth": 0, "outer_execution_id": None, "nested_execution_id": None}

    def reentrant_record_buy(**kwargs):
        execution_id = kwargs["execution_id"]
        if lifecycle["depth"] == 0:
            lifecycle["outer_execution_id"] = execution_id
            lifecycle["depth"] = 1
            try:
                assert _buy(executor, "600001")
            finally:
                lifecycle["depth"] = 0
            raise RuntimeError("forced outer recorder failure")
        lifecycle["nested_execution_id"] = execution_id
        return original_record_buy(**kwargs)

    monkeypatch.setattr(recorder, "记录买入", reentrant_record_buy)
    with pytest.raises(RuntimeError, match="forced outer recorder failure"):
        _buy(executor, "600001")

    outer_execution_id = lifecycle["outer_execution_id"]
    nested_execution_id = lifecycle["nested_execution_id"]
    assert isinstance(outer_execution_id, str) and outer_execution_id.strip()
    assert isinstance(nested_execution_id, str) and nested_execution_id.strip()
    assert nested_execution_id != outer_execution_id

    trades_by_execution = _trade_by_execution((executor,))
    approvals_by_execution = {
        row["execution_id"]: row
        for row in account.审批记录
        if row.get("execution_id")
    }
    assert outer_execution_id not in trades_by_execution
    assert outer_execution_id not in approvals_by_execution
    assert nested_execution_id in trades_by_execution
    assert nested_execution_id in approvals_by_execution

    nested_trade = trades_by_execution[nested_execution_id]
    nested_approval = approvals_by_execution[nested_execution_id]
    nested_approval_id = nested_trade.get("approval_id")
    assert isinstance(nested_approval_id, str) and nested_approval_id.strip()
    assert nested_approval_id == nested_approval.get("approval_id")
    assert account.持仓["600001"]["股数"] == nested_trade["成交数量"]
    assert len(account.审批记录) == 1
