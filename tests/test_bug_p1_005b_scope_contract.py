"""BUG-P1-005B red tests for scoped execution identity generation."""

from copy import deepcopy
from pathlib import Path

import pytest

from 策略引擎.规则执行器 import 规则执行器
from 策略引擎.交易账户 import 交易账户
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


def _shared_executors(monkeypatch):
    """Create two real executors sharing one deterministic account."""
    from 因子模块.因子管理器 import 因子管理器

    monkeypatch.setattr(
        因子管理器,
        "__init__",
        lambda self, config_dir: setattr(self, "已启用因子", {}),
    )
    account = 交易账户(1_000_000.0)
    run_parameters = {
        "共享账户模式": True,
        "多股资金池模式": True,
        "允许部分成交": True,
    }
    config = str(Path(__file__).parents[1] / "1_策略配置")
    first = 规则执行器(config, run_parameters, account, "600001")
    second = 规则执行器(config, run_parameters, account, "600002")
    return account, first, second


def _executor(account, stock, run_id, account_id, monkeypatch):
    from 因子模块.因子管理器 import 因子管理器

    monkeypatch.setattr(
        因子管理器,
        "__init__",
        lambda self, config_dir: setattr(self, "已启用因子", {}),
    )
    config = str(Path(__file__).parents[1] / "1_策略配置")
    return 规则执行器(
        config,
        {
            "共享账户模式": True,
            "多股资金池模式": True,
            "允许部分成交": True,
            "run_id": run_id,
            "account_id": account_id,
        },
        account,
        stock,
    )


def _bar(stock):
    return {
        "股票代码": stock,
        "前复权_开盘": 10.0,
        "前复权_收盘": 10.0,
        "前复权_最高": 12.0,
        "前复权_最低": 9.0,
        "不复权_开盘": 10.0,
        "不复权_收盘": 10.0,
        "日期": "2025-01-02",
        "完整时间": "2025-01-02 09:31",
        "成交量": 100_000,
        "ATR_14": 1.0,
    }


def _real_buy(executor, stock):
    executor.交易记录器.记录本根K线(
        0, "2025-01-02", "09:31", 10.0, 10.0, 50.0, 50.0, 1.0
    )
    executor.本根决策 = {
        "决策记录": {"买入": {}},
        "买入信号": [],
        "过滤检查": [],
    }
    return executor._执行买入(
        {}, _bar(stock), 0, 50.0,
        哨兵价=10.0, 信号类型="测试", 信号质量分=0.8,
        指定股数=100,
    )


def _real_sell(executor, stock, *, quantity_ratio=1.0):
    executor.本根决策 = {"决策记录": {"卖出": {}}}
    bar = _bar(stock)
    bar.update({"不复权_最高": 12.0, "不复权_最低": 9.0})
    position = executor.当前持仓[stock]
    return executor._执行卖出(
        position, {"说明": "测试卖出"}, 0.0, bar,
        股票代码=stock, 卖出比例=quantity_ratio,
    )


def _scope_state(account):
    scope = account._execution_scope
    return {
        "object": scope,
        "run_id": scope.get("run_id") if scope else None,
        "account_id": scope.get("account_id") if scope else None,
        "execution_ids": set(scope.get("execution_ids", set())) if scope else set(),
        "recorders": set(scope.get("recorders", set())) if scope else set(),
    }


def _account_state(account, recorder):
    return {
        "现金": account.现金,
        "持仓": deepcopy(account.持仓),
        "最新价格": deepcopy(account.最新价格),
        "审批记录": deepcopy(account.审批记录),
        "审批统计": deepcopy(account.审批统计),
        "拒绝序号": account.拒绝序号,
        "交易列表": deepcopy(recorder.交易列表),
    }


def _shared_state_snapshot(account, first, second):
    recorder_state = {}
    for name, executor in (("first", first), ("second", second)):
        recorder = executor.交易记录器
        recorder_state[name] = {
            "交易列表": deepcopy(recorder.交易列表),
            "买入序号": recorder.买入序号,
            "卖出序号": getattr(recorder, "卖出序号", None),
            "意图序号": recorder.意图序号,
            "订单序号": recorder.订单序号,
            "成交序号": recorder.成交序号,
        }
    strategy_state = {}
    for name, executor in (("first", first), ("second", second)):
        strategy_state[name] = {
            key: deepcopy(getattr(executor, key, None))
            for key in (
                "连续亏损次数", "冷却期剩余K线", "哨兵价已消费价格",
                "最近成交哨兵价", "哨兵价当前", "本根决策",
                "_本根已买入股票", "已实现损益", "未实现损益",
                "累计费用", "买入费用累计", "卖出费用累计",
            )
        }
    return {
        "现金": account.现金,
        "持仓": deepcopy(account.持仓),
        "审批记录": deepcopy(account.审批记录),
        "审批统计": deepcopy(account.审批统计),
        "拒绝序号": account.拒绝序号,
        "记录器": recorder_state,
        "策略": strategy_state,
    }


def test_same_run_same_account_different_stocks_have_distinct_execution_ids(monkeypatch):
    account, first_executor, second_executor = _shared_executors(monkeypatch)
    assert _real_buy(first_executor, "600001") is True
    assert _real_buy(second_executor, "600002") is True
    first = first_executor.交易记录器.交易列表[-1]
    second = second_executor.交易记录器.交易列表[-1]

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


def test_forced_duplicate_execution_id_fails_before_second_state_change(monkeypatch):
    account, first_executor, second_executor = _shared_executors(monkeypatch)
    assert _real_buy(first_executor, "600001") is True
    first = first_executor.交易记录器.交易列表[-1]
    before = _shared_state_snapshot(account, first_executor, second_executor)

    # Force the second real executor's generator back to the first ID.
    second_executor.交易记录器.成交序号 = 0
    caught = None
    try:
        _real_buy(second_executor, "600002")
    except Exception as error:  # capture to assert atomic rejection and state
        caught = error

    after = _shared_state_snapshot(account, first_executor, second_executor)
    assert after == before, "重复成交已在拒绝前改变账户、账本或策略状态"
    assert caught is not None, "重复 execution_id 必须在账户状态变化前拒绝"
    assert any(token in str(caught).lower() for token in ("execution", "重复", "唯一"))
    assert first["execution_id"]


def test_successful_actual_fills_have_nonempty_string_execution_ids():
    first = _buy(_recorder())
    second = _buy(_recorder())
    for row in (first, second):
        assert isinstance(row["execution_id"], str)
        assert row["execution_id"].strip()


def test_same_run_same_account_different_account_id_is_rejected_atomically(monkeypatch):
    account = 交易账户(1_000_000.0)
    first = _executor(account, "600001", "RUN-A", "ACCOUNT-A", monkeypatch)
    before = _scope_state(account)
    before_account = _account_state(account, first.交易记录器)
    caught = None
    try:
        _executor(account, "600002", "RUN-A", "ACCOUNT-B", monkeypatch)
    except Exception as error:
        caught = error

    after = _scope_state(account)
    assert after["object"] is before["object"]
    assert after["run_id"] == before["run_id"] == "RUN-A"
    assert after["account_id"] == before["account_id"] == "ACCOUNT-A"
    assert after["execution_ids"] == before["execution_ids"]
    assert after["recorders"] == before["recorders"]
    assert _account_state(account, first.交易记录器) == before_account
    assert first.交易记录器._execution_scope is before["object"]
    assert caught is not None, "同一 run/account 下的不同 account_id 必须拒绝绑定"


def test_same_account_different_run_id_is_rejected_without_scope_replacement(monkeypatch):
    account = 交易账户(1_000_000.0)
    first = _executor(account, "600001", "RUN-A", "ACCOUNT-A", monkeypatch)
    before = _scope_state(account)
    before_account = _account_state(account, first.交易记录器)
    caught = None
    try:
        _executor(account, "600002", "RUN-B", "ACCOUNT-A", monkeypatch)
    except Exception as error:
        caught = error

    after = _scope_state(account)
    assert after["object"] is before["object"]
    assert after["run_id"] == "RUN-A"
    assert after["account_id"] == "ACCOUNT-A"
    assert after["execution_ids"] == before["execution_ids"]
    assert after["recorders"] == before["recorders"]
    assert _account_state(account, first.交易记录器) == before_account
    assert first.交易记录器._execution_scope is before["object"]
    assert caught is not None, "同一账户不得通过覆盖 scope 切换 run_id"


def test_buy_record_failure_rolls_back_reserved_id_and_account(monkeypatch):
    account, executor, _ = _shared_executors(monkeypatch)
    before = _shared_state_snapshot(account, executor, executor)
    scope = account._execution_scope
    reserved_before = set(scope["execution_ids"])
    recorder = executor.交易记录器
    original_record = recorder.记录买入

    def fail_record(*args, **kwargs):
        raise RuntimeError("injected buy ledger failure")

    monkeypatch.setattr(recorder, "记录买入", fail_record)
    with pytest.raises(RuntimeError, match="injected buy ledger failure"):
        _real_buy(executor, "600001")
    monkeypatch.setattr(recorder, "记录买入", original_record)

    after = _shared_state_snapshot(account, executor, executor)
    assert after == before, "买入账本失败后账户、策略和审批状态必须原子回滚"
    assert set(scope["execution_ids"]) == reserved_before

    # Reusing the next candidate proves a failed reservation did not leave a ghost ID.
    recorder.成交序号 = 0
    assert _real_buy(executor, "600001") is True
    assert len(recorder.交易列表) == 1
    assert set(scope["execution_ids"]) == {recorder.交易列表[0]["execution_id"]}


def test_sell_record_failure_rolls_back_reserved_id_and_account(monkeypatch):
    account, executor, _ = _shared_executors(monkeypatch)
    assert _real_buy(executor, "600001") is True
    assert _real_buy(executor, "600001") is True
    # Two lots ensure a half-size sell leaves a position for the retry.
    before = _shared_state_snapshot(account, executor, executor)
    scope = account._execution_scope
    reserved_before = set(scope["execution_ids"])
    recorder = executor.交易记录器
    original_record = recorder.记录卖出

    def fail_record(*args, **kwargs):
        raise RuntimeError("injected sell ledger failure")

    monkeypatch.setattr(recorder, "记录卖出", fail_record)
    with pytest.raises(RuntimeError, match="injected sell ledger failure"):
        _real_sell(executor, "600001", quantity_ratio=0.5)
    monkeypatch.setattr(recorder, "记录卖出", original_record)

    after = _shared_state_snapshot(account, executor, executor)
    assert after == before, "卖出账本失败后账户、策略和审批状态必须原子回滚"
    assert set(scope["execution_ids"]) == reserved_before

    recorder.成交序号 = 2
    assert _real_sell(executor, "600001", quantity_ratio=0.5) is True
    assert len(recorder.交易列表) == 3
    assert len(set(row["execution_id"] for row in recorder.交易列表)) == 3


def test_interleaved_real_executors_have_stable_distinct_execution_ids(monkeypatch):
    account, first, second = _shared_executors(monkeypatch)
    assert _real_buy(first, "600001") is True
    first_row = first.交易记录器.交易列表[-1]
    assert _real_buy(second, "600002") is True
    second_row = second.交易记录器.交易列表[-1]
    assert _real_buy(first, "600001") is True
    third_row = first.交易记录器.交易列表[-1]
    rows = [first_row, second_row, third_row]
    ids = [row["execution_id"] for row in rows]
    assert all(isinstance(value, str) and value.strip() for value in ids)
    assert len(set(ids)) == 3
    assert ids == sorted(ids)


def test_buy_and_sell_share_one_execution_namespace(monkeypatch):
    account, executor, _ = _shared_executors(monkeypatch)
    assert _real_buy(executor, "600001") is True
    assert _real_sell(executor, "600001") is True
    rows = executor.交易记录器.交易列表
    assert len(rows) == 2
    assert rows[0]["execution_id"] != rows[1]["execution_id"]
    assert all(row["execution_id"] in account._execution_scope["execution_ids"] for row in rows)


def test_reusing_a_successfully_submitted_reserved_id_is_rejected_atomically(monkeypatch):
    account, executor, _ = _shared_executors(monkeypatch)
    recorder = executor.交易记录器
    assert _real_buy(executor, "600001") is True
    row = recorder.交易列表[0]
    before = _shared_state_snapshot(account, executor, executor)
    caught = None
    try:
        recorder.记录买入(
            10.0, "测试重复", 0.8, 1000.0, 10.0, 10.0,
            时间="2025-01-02 09:31", 成交数量=100, 交易费用=5.0,
            总成本=1005.0, execution_id=row["execution_id"],
        )
    except Exception as error:
        caught = error

    after = _shared_state_snapshot(account, executor, executor)
    assert after == before
    assert caught is not None
    assert any(token in str(caught).lower() for token in ("execution", "重复", "唯一"))


def _approval_state(account):
    return {
        "现金": deepcopy(account._last_approval_cash),
        "持仓": deepcopy(account._last_approval_positions),
    }


def test_buy_failure_restores_calling_decisions_and_recent_decision(monkeypatch):
    account, executor, _ = _shared_executors(monkeypatch)
    decision = {"marker": "BUY-CALL", "nested": {"values": [1, 2, 3]}}
    recent = {"marker": "BUY-RECENT", "nested": {"values": [9]}}
    executor.本根决策 = deepcopy(decision)
    executor._最近成功决策 = deepcopy(recent)
    before = _shared_state_snapshot(account, executor, executor)
    recorder = executor.交易记录器

    def fail_record(*args, **kwargs):
        raise RuntimeError("injected buy decision rollback failure")

    monkeypatch.setattr(recorder, "记录买入", fail_record)
    with pytest.raises(RuntimeError, match="injected buy decision rollback failure"):
        _real_buy(executor, "600001")

    assert executor.本根决策 == decision
    assert executor._最近成功决策 == recent
    assert executor.本根决策 != {}
    assert executor.本根决策 != executor._最近成功决策
    assert _shared_state_snapshot(account, executor, executor) == before


def test_sell_failure_restores_calling_decisions_and_recent_decision(monkeypatch):
    account, executor, _ = _shared_executors(monkeypatch)
    assert _real_buy(executor, "600001") is True
    decision = {"marker": "SELL-CALL", "nested": {"values": [4, 5]}}
    recent = {"marker": "SELL-RECENT", "nested": {"values": [8, 9]}}
    executor.本根决策 = deepcopy(decision)
    executor._最近成功决策 = deepcopy(recent)
    before = _shared_state_snapshot(account, executor, executor)
    recorder = executor.交易记录器

    def fail_record(*args, **kwargs):
        raise RuntimeError("injected sell decision rollback failure")

    monkeypatch.setattr(recorder, "记录卖出", fail_record)
    with pytest.raises(RuntimeError, match="injected sell decision rollback failure"):
        _real_sell(executor, "600001")

    assert executor.本根决策 == decision
    assert executor._最近成功决策 == recent
    assert executor.本根决策 != executor._最近成功决策
    assert _shared_state_snapshot(account, executor, executor) == before


def test_buy_approval_internal_snapshot_rolls_back_after_late_failure(monkeypatch):
    account, executor, _ = _shared_executors(monkeypatch)
    account._last_approval_cash = 12345.67
    account._last_approval_positions = {"sentinel": 7}
    before_account = _approval_state(account)
    before = _shared_state_snapshot(account, executor, executor)
    original_approval = executor._记录账户审批
    observed = {}

    def fail_after_approval(**row):
        original_approval(**row)
        observed["state"] = _approval_state(account)
        raise RuntimeError("injected buy post-approval failure")

    monkeypatch.setattr(executor, "_记录账户审批", fail_after_approval)
    with pytest.raises(RuntimeError, match="injected buy post-approval failure"):
        _real_buy(executor, "600001")

    assert observed["state"] != before_account
    assert observed["state"]["持仓"] != before_account["持仓"]
    assert _shared_state_snapshot(account, executor, executor) == before
    assert _approval_state(account) == before_account


def test_sell_approval_internal_snapshot_rolls_back_after_late_failure(monkeypatch):
    account, executor, _ = _shared_executors(monkeypatch)
    assert _real_buy(executor, "600001") is True
    account._last_approval_cash = 23456.78
    account._last_approval_positions = {"sentinel": 8}
    before_account = _approval_state(account)
    before = _shared_state_snapshot(account, executor, executor)
    original_approval = executor._记录账户审批
    observed = {}

    def fail_after_approval(**row):
        original_approval(**row)
        observed["state"] = _approval_state(account)
        raise RuntimeError("injected sell post-approval failure")

    monkeypatch.setattr(executor, "_记录账户审批", fail_after_approval)
    with pytest.raises(RuntimeError, match="injected sell post-approval failure"):
        _real_sell(executor, "600001")

    assert observed["state"] != before_account
    assert observed["state"]["持仓"] != before_account["持仓"]
    assert _shared_state_snapshot(account, executor, executor) == before
    assert _approval_state(account) == before_account


def test_legal_buy_and_sell_update_decisions_approval_and_execution_normally(monkeypatch):
    account, executor, _ = _shared_executors(monkeypatch)
    initial_approval = _approval_state(account)
    assert _real_buy(executor, "600001") is True
    assert executor.本根决策
    assert executor._最近成功决策 == executor.本根决策
    after_buy_approval = _approval_state(account)
    assert after_buy_approval != initial_approval
    assert len(executor.交易记录器.交易列表) == 1

    assert _real_sell(executor, "600001") is True
    assert executor.本根决策["决策记录"]["卖出"]["成交数量"] > 0
    assert _approval_state(account) != after_buy_approval
    rows = executor.交易记录器.交易列表
    assert len(rows) == 2
    assert rows[0]["execution_id"] != rows[1]["execution_id"]
