"""BUG-P1-005C control tests, independent from red assertions."""

import pytest

from test_bug_p1_005c_approval_link_v2_support import (
    _buy,
    _ordered_approval_rows,
    _sell,
    _trade_by_execution,
    executor_factory,
)


def test_control_lifecycle_ids_match_after_shuffling_approvals(executor_factory):
    account, first = executor_factory(stock="600001")
    _, second = executor_factory(account=account, stock="600002")
    assert _buy(first, "600001")
    assert _buy(second, "600002")
    assert _sell(first, "600001")

    trades = _trade_by_execution((first, second))
    approvals = {
        row["execution_id"]: row
        for row in _ordered_approval_rows(account, trades, descending=True)
    }
    assert set(trades) == set(approvals)
    for execution_id, trade in trades.items():
        approval = approvals[execution_id]
        assert trade["intent_id"] == approval["intent_id"]
        assert trade["order_id"] == approval["order_id"]


@pytest.mark.parametrize("descending", [False, True])
def test_control_approval_order_is_not_part_of_matching(executor_factory, descending):
    account, first = executor_factory(stock="600001")
    _, second = executor_factory(account=account, stock="600002")
    assert _buy(first, "600001")
    assert _buy(second, "600002")
    trades = _trade_by_execution((first, second))
    by_execution = {
        row["execution_id"]: row
        for row in _ordered_approval_rows(account, trades, descending=descending)
    }
    for execution_id, trade in trades.items():
        assert by_execution[execution_id]["intent_id"] == trade["intent_id"]
        assert by_execution[execution_id]["order_id"] == trade["order_id"]


def test_control_shared_account_a_b_a_reconciles_by_ids_after_shuffle(executor_factory):
    account, first = executor_factory(stock="600001")
    _, second = executor_factory(account=account, stock="600002")
    assert _buy(first, "600001")
    assert _buy(second, "600002")
    assert _buy(first, "600001")

    trades = _trade_by_execution((first, second))
    approvals = {
        row["execution_id"]: row
        for row in _ordered_approval_rows(account, trades, descending=True)
    }
    assert set(trades) == set(approvals)
    for execution_id, trade in trades.items():
        approval = approvals[execution_id]
        assert approval["intent_id"] == trade["intent_id"]
        assert approval["order_id"] == trade["order_id"]
        assert approval["execution_id"] == execution_id


def test_control_two_real_account_scopes_reconcile_independently(executor_factory):
    first_account, first = executor_factory(stock="600001", account_id="ACCOUNT-A")
    second_account, second = executor_factory(stock="600001", account_id="ACCOUNT-B")
    assert _buy(first, "600001")
    assert _buy(second, "600001")

    for account, executor in ((first_account, first), (second_account, second)):
        trades = _trade_by_execution((executor,))
        approvals = {
            row["execution_id"]: row
            for row in _ordered_approval_rows(account, trades)
        }
        assert set(trades) == set(approvals)
        for execution_id, trade in trades.items():
            assert approvals[execution_id]["execution_id"] == execution_id
