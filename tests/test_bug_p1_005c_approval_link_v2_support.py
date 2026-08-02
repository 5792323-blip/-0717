from copy import deepcopy
from pathlib import Path

import pytest

from 因子模块.因子管理器 import 因子管理器
from 策略引擎.规则执行器 import 规则执行器
from 策略引擎.交易账户 import 交易账户


@pytest.fixture
def executor_factory(monkeypatch):
    monkeypatch.setattr(
        因子管理器,
        "__init__",
        lambda self, config_dir: setattr(self, "已启用因子", {}),
    )

    def make(account=None, stock="600001", run_id="RUN-005C-V2", account_id="ACCOUNT-005C-V2"):
        account = account or 交易账户(1_000_000.0)
        params = {
            "共享账户模式": True,
            "多股资金池模式": True,
            "允许部分成交": True,
            "run_id": run_id,
            "account_id": account_id,
        }
        config = str(Path(__file__).parents[1] / "1_策略配置")
        return account, 规则执行器(config, params, account, stock)

    return make


def _bar(stock, date="2025-01-02"):
    return {
        "股票代码": stock,
        "前复权_开盘": 10.0,
        "前复权_收盘": 10.0,
        "前复权_最高": 12.0,
        "前复权_最低": 9.0,
        "不复权_开盘": 10.0,
        "不复权_收盘": 10.0,
        "日期": date,
        "完整时间": f"{date} 09:31",
        "成交量": 100_000,
        "ATR_14": 1.0,
    }


def _buy(executor, stock, quantity=100, date="2025-01-02"):
    args = _buy_arguments(executor, stock, quantity, date)
    return executor._执行买入(
        *args, 哨兵价=10.0, 信号类型="测试", 信号质量分=0.8, 指定股数=quantity,
    )


def _buy_arguments(executor, stock, quantity=100, date="2025-01-02"):
    executor.交易记录器.记录本根K线(0, date, "09:31", 10.0, 10.0, 50.0, 50.0, 1.0)
    executor.本根决策 = {"决策记录": {"买入": {}}, "买入信号": [], "过滤检查": []}
    return ({}, _bar(stock, date), 0, 50.0)


def _sell(executor, stock):
    executor.本根决策 = {"决策记录": {"卖出": {}}}
    return executor._执行卖出(
        executor.当前持仓[stock], {"说明": "测试卖出"}, 0.0, _bar(stock),
        股票代码=stock, 卖出比例=1.0,
    )


def _trade_by_execution(executors):
    trades = [trade for executor in executors for trade in executor.交易记录器.交易列表]
    return {trade["execution_id"]: trade for trade in trades if trade.get("execution_id")}


def _approval_rows_by_execution(account):
    return {
        row["execution_id"]: row
        for row in account.审批记录
        if row.get("execution_id")
    }


def _ordered_approval_rows(account, execution_ids, descending=False):
    """Return a deterministic permutation keyed only by lifecycle identity."""
    approvals = {
        execution_id: row
        for execution_id, row in _approval_rows_by_execution(account).items()
        if execution_id in execution_ids
    }
    return sorted(
        approvals.values(),
        key=lambda row: row["execution_id"],
        reverse=descending,
    )


def _transaction_state(executor):
    account = executor.账户
    recorder = executor.交易记录器
    scope = account._execution_scope
    return {
        "account_cash": account.现金,
        "account_holdings": deepcopy(account.持仓),
        "approvals": deepcopy(account.审批记录),
        "approval_stats": deepcopy(account.审批统计),
        "rejection_sequence": account.拒绝序号,
        "scope_execution_ids": set(scope["execution_ids"]),
        "scope_pending": dict(scope["pending_execution_ids"]),
        "scope_committed": set(scope["committed_execution_ids"]),
        "recorder_trades": deepcopy(recorder.交易列表),
        "recorder_positions": deepcopy(recorder.持仓记录),
        "recorder_counters": {
            name: getattr(recorder, name)
            for name in ("买入序号", "持仓组序号", "意图序号", "订单序号", "成交序号")
        },
        "executor_cash": executor.当前现金,
        "executor_positions": deepcopy(executor.当前持仓),
    }
