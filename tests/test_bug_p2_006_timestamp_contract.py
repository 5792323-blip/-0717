"""BUG-P2-006: canonical execution-time contract (方案 B).

Only this file is changed in this round.  The tests deliberately remain red
until production validates the canonical ``时间`` before any state mutation.
"""

from types import SimpleNamespace

import pandas as pd
import pytest

from 组合回测.统一多股执行器 import _写入股票归因过程, _股票归因
from 策略引擎.交易账户 import 交易账户
from 策略引擎.交易记录器 import 交易记录器
from 策略引擎.规则执行器 import 规则执行器


BAD_TIMES = [None, "", pd.NaT, "not-a-date"]


def _snapshot(executor):
    return {
        "现金": executor.当前现金,
        "持仓": repr(executor.当前持仓),
        "交易列表": len(executor.交易记录器.交易列表),
        "买入序号": executor.交易记录器.买入序号,
        "订单序号": executor.交易记录器.订单序号,
        "成交序号": executor.交易记录器.成交序号,
        "审批": len(getattr(executor.账户, "审批记录", [])),
    }


def _buy_executor():
    account = 交易账户(100_000)
    executor = object.__new__(规则执行器)
    executor.账户 = account
    executor.账户视图 = account.股票视图("600001")
    executor.运行参数 = {"共享账户模式": True}
    executor._当前现金 = 100_000.0
    executor._当前持仓 = {}
    executor.交易记录器 = 交易记录器()
    executor.交易记录器.记录本根K线(0, "2025-01-02", "09:31", 10, 10, 30, 30, 1)
    executor.本根决策 = {"决策记录": {"买入": {}}, "动作原因": ""}
    executor.已买入K线数 = 0
    executor.价格序列 = []
    executor.上一根_不复权收盘 = 10
    executor.上一根_RSI_MA = 30
    executor.大盘状态 = "震荡模式"
    executor.有底背离 = False
    executor.有顶背离 = False
    executor.预测器 = SimpleNamespace(model=None)
    executor.信号质量对照 = {}
    executor.哨兵价形成类型 = "RSI上穿20"
    executor.买入时机模式 = "precomputed_stop_entry"
    executor.买入溢价 = 1.0
    executor.滑点 = 0.001
    executor.佣金率 = 0.00025
    executor.印花税率 = 0.001
    executor.过户费率 = 0.00001
    executor.基础单只金额 = 10_000
    executor.最大单只比例 = 0.0
    executor.最大总仓位比例 = 0.0
    executor.现金底线比例 = 0.0
    executor.单股全仓模式 = False
    executor.流动性上限比例 = None
    executor.因子管理器 = None
    executor._计算账户结构性可用金额 = lambda price: (100_000.0, {})
    executor._最低交易单位 = lambda stock: 100
    executor._获取买入规则 = lambda signal: {"信号资金系数": 1.0}
    return executor


def _buy_bar(bad_time):
    return {
        "股票代码": "600001", "完整时间": bad_time, "日期": bad_time,
        "前复权_开盘": 10.0, "前复权_最高": 11.0, "前复权_最低": 9.0,
        "前复权_收盘": 10.0, "不复权_开盘": 10.0,
        "不复权_最高": 11.0, "不复权_最低": 9.0, "不复权_收盘": 10.0,
    }


@pytest.mark.parametrize("bad_time", BAD_TIMES)
def test_invalid_buy_time_fails_before_any_account_or_ledger_mutation(bad_time):
    executor = _buy_executor()
    before = _snapshot(executor)
    error = None
    try:
        executor._执行买入(
            None, _buy_bar(bad_time), 0, 20, 哨兵价=10,
            信号类型="RSI上穿20", 信号质量分=1.0,
        )
    except Exception as exc:  # record current failure boundary for the red test
        error = exc
    assert _snapshot(executor) == before
    assert not executor.账户.审批记录
    assert isinstance(error, (AssertionError, ValueError)) and "时间" in str(error)


def _sell_executor(bad_time):
    executor = _buy_executor()
    executor._当前持仓 = {
        "600001": {"股数": 100, "买入时间": 0, "成本": 1000.0,
                   "总成本": 1001.0, "持仓组ID": "G1", "RSI峰值": 30.0}
    }
    executor.账户.持仓["600001"] = executor._当前持仓["600001"]
    executor.已买入K线数 = 2
    executor.连续亏损次数 = 2
    executor.冷却期剩余K线 = 0
    executor.本根决策 = {"决策记录": {"卖出": {}}, "动作原因": ""}
    executor._sell_bar = {"股票代码": "600001", "日期": bad_time,
                          "前复权_开盘": 10.0, "不复权_开盘": 10.0,
                          "不复权_最低": 9.0, "不复权_最高": 11.0}
    return executor


@pytest.mark.parametrize("bad_time", BAD_TIMES)
def test_invalid_sell_time_fails_before_cash_position_and_strategy_mutation(bad_time):
    executor = _sell_executor(bad_time)
    before = _snapshot(executor)
    before_loss = executor.连续亏损次数
    before_cooldown = executor.冷却期剩余K线
    error = None
    try:
        executor._执行卖出(
            executor.当前持仓["600001"], {"说明": "测试卖出"}, -0.1,
            executor._sell_bar, 触发价=10, 股票代码="600001",
        )
    except Exception as exc:
        error = exc
    assert _snapshot(executor) == before
    assert executor.连续亏损次数 == before_loss
    assert executor.冷却期剩余K线 == before_cooldown
    assert isinstance(error, (AssertionError, ValueError)) and "时间" in str(error)


@pytest.mark.parametrize("kwargs", [
    {"时间": None, "日期": ""},
    {"时间": "", "日期": ""},
    {"时间": pd.NaT, "日期": ""},
    {"时间": "bad", "日期": "bad"},
])
def test_recorder_rejects_invalid_time_before_sequence_id_and_append(kwargs):
    recorder = 交易记录器()
    recorder.记录本根K线(0, "2025-01-02", "09:31", 10, 10, 30, 30, 1)
    before = (len(recorder.交易列表), recorder.买入序号, recorder.订单序号, recorder.成交序号)
    with pytest.raises((AssertionError, ValueError), match="成交时间|时间"):
        recorder.记录买入(10, "test", 1, 1000, 10, 10, **kwargs,
                         成交数量=100, 交易费用=1, 总成本=1001)
    assert (len(recorder.交易列表), recorder.买入序号, recorder.订单序号, recorder.成交序号) == before


def test_recorder_only_date_is_normalized_at_write_boundary():
    recorder = 交易记录器()
    recorder.记录本根K线(0, "2025-01-02", "09:31", 10, 10, 30, 30, 1)
    recorder.记录买入(10, "test", 1, 1000, 10, 10, 日期="2025-01-02",
                     成交数量=100, 交易费用=1, 总成本=1001)
    assert recorder.交易列表[-1]["时间"] == "2025-01-02"


def test_recorder_rejects_conflicting_time_and_date():
    recorder = 交易记录器()
    recorder.记录本根K线(0, "2025-01-02", "09:31", 10, 10, 30, 30, 1)
    with pytest.raises((AssertionError, ValueError), match="日期|时间"):
        recorder.记录买入(10, "test", 1, 1000, 10, 10,
                         时间="2025-01-03", 日期="2025-01-02",
                         成交数量=100, 交易费用=1, 总成本=1001)


def test_final_and_process_attribution_share_invalid_time_failure_semantics():
    trades = pd.DataFrame([{
        "时间": None, "类型": "买入", "成交数量": 100,
        "总成本": 1001.0, "交易费用": 1.0, "execution_id": "X1",
    }])
    process = pd.DataFrame([
        {"时间": "2025-01-01", "持仓市值": 0},
        {"时间": "2025-01-03", "持仓市值": 1000},
    ])
    with pytest.raises((AssertionError, ValueError), match="成交时间|时间"):
        _股票归因(trades, ending_value=1000)
    with pytest.raises((AssertionError, ValueError), match="成交时间|时间"):
        _写入股票归因过程(process, trades)


def test_date_only_ledger_is_rejected_by_attribution_layer():
    trades = pd.DataFrame([{
        "日期": "2025-01-02", "类型": "买入", "成交数量": 100,
        "总成本": 1001.0, "交易费用": 1.0, "execution_id": "X1",
    }])
    with pytest.raises((AssertionError, ValueError), match="时间|成交"):
        _股票归因(trades, ending_value=1000)
    with pytest.raises((AssertionError, ValueError), match="时间|成交"):
        _写入股票归因过程(pd.DataFrame([{"时间": "2025-01-03", "持仓市值": 0}]), trades)


def test_attribution_rejects_conflicting_trade_time_and_date():
    """归因层不得接受日历日期与规范成交时间冲突的账本行。"""
    trades = pd.DataFrame([{
        "时间": "2025-01-02 09:31", "日期": "2025-01-03",
        "类型": "买入", "成交数量": 100, "总成本": 1001.0,
        "交易费用": 1.0, "execution_id": "X-CONFLICT",
    }])

    with pytest.raises((AssertionError, ValueError), match="日期|时间|冲突"):
        _股票归因(trades, ending_value=1000)
    with pytest.raises((AssertionError, ValueError), match="日期|时间|冲突"):
        _写入股票归因过程(
            pd.DataFrame([{"时间": "2025-01-03", "持仓市值": 0}]),
            trades,
        )


def test_attribution_accepts_consistent_trade_time_and_date():
    trades = pd.DataFrame([{
        "时间": "2025-01-02 09:31", "日期": "2025-01-02",
        "类型": "买入", "成交数量": 100, "总成本": 1001.0,
        "交易费用": 1.0, "execution_id": "X-CONSISTENT",
    }])

    result = _股票归因(trades, ending_value=1000)
    assert result["持仓数量"] == 100
    process = _写入股票归因过程(
        pd.DataFrame([{"时间": "2025-01-02 09:31", "持仓市值": 1000}]),
        trades,
    )
    assert process.loc[0, "持仓成本"] == pytest.approx(1001.0)


def test_valid_buy_and_sell_still_have_one_timestamped_execution_each():
    recorder = 交易记录器()
    recorder.记录本根K线(0, "2025-01-02", "09:31", 10, 10, 30, 30, 1)
    recorder.记录买入(10, "test", 1, 1000, 10, 10, 时间="2025-01-02 09:31",
                     成交数量=100, 交易费用=1, 总成本=1001)
    assert len(recorder.交易列表) == 1
    assert recorder.交易列表[0]["execution_id"]
    assert recorder.交易列表[0]["时间"] == "2025-01-02 09:31"
    recorder.记录卖出(10.5, "test sell", 0.04, 1,
                       时间="2025-01-03 09:31", 成交数量=100)
    assert len(recorder.交易列表) == 2
    assert recorder.交易列表[1]["execution_id"]
    assert recorder.交易列表[1]["时间"] == "2025-01-03 09:31"
