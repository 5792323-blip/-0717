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
                "_本根已买入股票",
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
