"""BUG-P1-005C red tests for explicit approval linkage."""

import pytest

from test_bug_p1_005c_approval_link_v2_support import (
    _buy,
    _buy_arguments,
    _sell,
    _trade_by_execution,
    _transaction_state,
    executor_factory,
)


def test_red_buy_trade_requires_explicit_approval_id(executor_factory):
    account, executor = executor_factory(stock="600001")
    captured = {}
    original = executor.交易记录器.记录买入

    def capture(**kwargs):
        captured.update(kwargs)
        return original(**kwargs)

    executor.交易记录器.记录买入 = capture
    assert _buy(executor, "600001")
    execution_id = captured["execution_id"]
    trade = _trade_by_execution((executor,))[execution_id]
    approval = {
        row["execution_id"]: row
        for row in account.审批记录
        if row.get("execution_id")
    }[execution_id]
    approval_id = captured.get("approval_id")
    assert isinstance(approval_id, str) and approval_id.strip()
    assert trade.get("approval_id") == approval_id == approval.get("approval_id")


def test_red_sell_trade_requires_explicit_approval_id(executor_factory):
    account, executor = executor_factory(stock="600001")
    assert _buy(executor, "600001")
    captured = {}
    original = executor.交易记录器.记录卖出

    def capture(**kwargs):
        captured.update(kwargs)
        return original(**kwargs)

    executor.交易记录器.记录卖出 = capture
    assert _sell(executor, "600001")
    execution_id = captured["execution_id"]
    trade = _trade_by_execution((executor,))[execution_id]
    approval = {
        row["execution_id"]: row
        for row in account.审批记录
        if row.get("execution_id")
    }[execution_id]
    approval_id = captured.get("approval_id")
    assert isinstance(approval_id, str) and approval_id.strip()
    assert trade.get("approval_id") == approval_id == approval.get("approval_id")


def test_red_rejected_approval_id_is_not_inherited_by_later_execution(executor_factory):
    account, executor = executor_factory(stock="600001")
    account.现金 = 1.0
    assert _buy(executor, "600001") is False
    rejected_rows = {
        row.get("rejection_id"): row
        for row in account.审批记录
        if row.get("rejection_id")
    }
    assert len(rejected_rows) == 1
    rejected = _single_mapping_value(rejected_rows)
    rejected_approval_id = rejected.get("approval_id")
    assert isinstance(rejected_approval_id, str) and rejected_approval_id.strip()

    account.现金 = 1_000_000.0
    assert _buy(executor, "600001")
    trades = _trade_by_execution((executor,))
    successful = {
        row["execution_id"]: row
        for row in account.审批记录
        if row.get("execution_id")
    }
    assert len(successful) == 1
    execution_id, approval = _single_mapping_item(successful)
    trade = trades[execution_id]
    assert approval.get("approval_id") != rejected_approval_id
    assert trade.get("approval_id") == approval.get("approval_id")


def test_red_approval_id_is_distinct_from_other_lifecycle_ids(executor_factory):
    account, executor = executor_factory(stock="600001")
    assert _buy(executor, "600001")
    trades = _trade_by_execution((executor,))
    approvals = {
        row["execution_id"]: row
        for row in account.审批记录
        if row.get("execution_id")
    }
    assert len(approvals) == 1
    execution_id, approval = _single_mapping_item(approvals)
    trade = trades[execution_id]
    approval_id = approval.get("approval_id")
    assert isinstance(approval_id, str) and approval_id.strip()
    assert approval_id not in {
        trade.get("intent_id"), trade.get("order_id"), trade.get("execution_id"),
        trade.get("rejection_id"), approval.get("rejection_id"),
    }


def test_red_trade_write_failure_rolls_back_approval_and_allocator_state(executor_factory, monkeypatch):
    account, executor = executor_factory(stock="600001")
    args = _buy_arguments(executor, "600001")
    before = _transaction_state(executor)
    captured = {}

    def fail(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("forced trade write failure")

    monkeypatch.setattr(executor.交易记录器, "记录买入", fail)
    with pytest.raises(RuntimeError, match="forced trade write failure"):
        executor._执行买入(
            *args, 哨兵价=10.0, 信号类型="测试", 信号质量分=0.8, 指定股数=100,
        )

    after = _transaction_state(executor)
    assert after == before
    assert isinstance(captured.get("approval_id"), str) and captured["approval_id"].strip()


def test_red_shared_account_a_b_a_approval_ids_are_explicit_and_unique(executor_factory):
    account, first = executor_factory(stock="600001")
    _, second = executor_factory(account=account, stock="600002")
    assert _buy(first, "600001")
    assert _buy(second, "600002")
    assert _buy(first, "600001")
    trades = _trade_by_execution((first, second))
    approvals = {
        row["execution_id"]: row
        for row in account.审批记录
        if row.get("execution_id")
    }
    assert set(trades) == set(approvals)
    approval_ids = set()
    for execution_id, trade in trades.items():
        approval = approvals[execution_id]
        approval_id = trade.get("approval_id")
        assert isinstance(approval_id, str) and approval_id.strip()
        assert approval_id == approval.get("approval_id")
        assert approval_id not in approval_ids
        approval_ids.add(approval_id)


def test_red_two_account_scopes_have_independent_approval_links(executor_factory):
    first_account, first = executor_factory(stock="600001", account_id="ACCOUNT-A")
    second_account, second = executor_factory(stock="600001", account_id="ACCOUNT-B")
    assert _buy(first, "600001")
    assert _buy(second, "600001")
    for account, executor in ((first_account, first), (second_account, second)):
        trades = _trade_by_execution((executor,))
        approvals = {
            row["execution_id"]: row
            for row in account.审批记录
            if row.get("execution_id")
        }
        assert set(trades) == set(approvals)
        for execution_id, trade in trades.items():
            approval = approvals[execution_id]
            approval_id = trade.get("approval_id")
            assert isinstance(approval_id, str) and approval_id.strip()
            assert approval_id == approval.get("approval_id")


def _single_mapping_item(mapping):
    assert len(mapping) == 1
    for key, value in mapping.items():
        return key, value


def _single_mapping_value(mapping):
    assert len(mapping) == 1
    for value in mapping.values():
        return value
