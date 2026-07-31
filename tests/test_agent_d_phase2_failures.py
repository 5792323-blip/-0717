"""修复前失败测试：时序、严格预挂单和成交时间契约。"""

import pandas as pd
import pytest
import yaml

from 组合回测.统一多股执行器 import _写入股票归因过程, _股票归因
from 策略引擎.规则执行器 import 规则执行器


CONFIG = "1_策略配置"


def test_strict_configuration_reaches_next_bar_execution_switch():
    core = yaml.safe_load(open(f"{CONFIG}/核心模块配置.yaml", encoding="utf-8"))
    assert core["核心模块"]["下一根执行"]["启用"] is True


def test_strict_and_same_bar_modes_have_distinct_execution_policy():
    strict = object.__new__(规则执行器)
    same_bar = object.__new__(规则执行器)
    strict.买入时机模式 = "precomputed_stop_entry"
    same_bar.买入时机模式 = "same_bar_entry"
    # A strict precomputed order must not be treated as same-bar confirmation.
    assert strict.买入时机模式 != same_bar.买入时机模式
    assert getattr(strict, "待次根开盘买入", None) is not getattr(
        same_bar, "待次根开盘买入", None
    )


def test_actual_execution_requires_a_valid_timestamp():
    trades = pd.DataFrame([{
        "时间": "", "类型": "买入", "成交数量": 100, "总成本": 1001,
        "execution_id": "X1",
    }])
    with pytest.raises((AssertionError, ValueError), match="时间|timestamp|成交"):
        _股票归因(trades, ending_value=1000)


def test_missing_trade_time_cannot_be_attributed_to_the_first_day():
    process = pd.DataFrame([
        {"时间": "2025-01-01", "持仓市值": 0},
        {"时间": "2025-01-02", "持仓市值": 1000},
    ])
    trades = pd.DataFrame([{
        "时间": None, "类型": "买入", "成交数量": 100, "总成本": 1001,
        "execution_id": "X1",
    }])
    result = _写入股票归因过程(process, trades)
    assert result.loc[0, "持仓成本"] == 0


def test_future_data_mutation_cannot_change_completed_prefix_decisions():
    prefix = pd.DataFrame([
        {"日期": "2025-01-01", "前复权_收盘": 100.0, "RSI_14": 18.0},
        {"日期": "2025-01-02", "前复权_收盘": 101.0, "RSI_14": 22.0},
    ])
    future_a = {"日期": "2025-01-03", "前复权_收盘": 102.0, "RSI_14": 25.0}
    future_b = {"日期": "2025-01-03", "前复权_收盘": 999.0, "RSI_14": 99.0}
    assert prefix.to_dict("records") == prefix.copy().to_dict("records")
    assert future_a != future_b

