from 买入执行模块.entry_timing import (
    CLOSE_NEXT_OPEN, LEGACY_SAME_BAR, STRICT_PRECOMPUTED, TB_REPLAY, 哨兵价可执行, 允许旧版本根回填,
)
from 成交模型.buy_fill_model import 计算买入成交
from 买入执行模块.sentinel_trigger import 评估触发


def trigger_bar(high, close=1.0, rsi=1.0):
    # close/rsi 故意可变；严格触发模块不得读取它们。
    return {
        "前复权_开盘": 99.0, "不复权_开盘": 99.0,
        "前复权_最高": high, "前复权_收盘": close, "RSI_14": rsi,
    }


def test_strict_precomputed_order_does_not_need_current_close_rsi_confirmation():
    assert 哨兵价可执行(STRICT_PRECOMPUTED, 已确认=False, 当根收盘发生上穿=False) is True


def test_legacy_order_keeps_old_same_bar_confirmation_only_for_comparison():
    assert 哨兵价可执行(LEGACY_SAME_BAR, 已确认=False, 当根收盘发生上穿=False) is False
    assert 哨兵价可执行(LEGACY_SAME_BAR, 已确认=False, 当根收盘发生上穿=True) is True
    assert 哨兵价可执行(TB_REPLAY, 已确认=False, 当根收盘发生上穿=True) is True


def test_close_confirmation_is_a_separate_mode():
    assert CLOSE_NEXT_OPEN != STRICT_PRECOMPUTED


def test_strict_modes_force_block_legacy_same_bar_backfill():
    assert 允许旧版本根回填(STRICT_PRECOMPUTED) is False
    assert 允许旧版本根回填(CLOSE_NEXT_OPEN) is False
    assert 允许旧版本根回填(LEGACY_SAME_BAR) is True
    assert 允许旧版本根回填(TB_REPLAY) is True


def test_premium_above_bar_high_must_not_fill():
    result = 计算买入成交(100, 105, 98, 105, 1.001)
    assert result["可成交"] is False
    assert "最高价" in result["原因"]


def test_gap_and_intrabar_fills_stay_inside_ohlc():
    gap = 计算买入成交(110, 112, 108, 105, 1.001)
    touch = 计算买入成交(100, 108, 99, 105, 1.001)
    assert gap["可成交"] and 108 <= gap["成交价"] <= 112
    assert touch["可成交"] and 99 <= touch["成交价"] <= 108


def test_reverse_below_previous_high_requires_strict_previous_high_breakout():
    equal = 评估触发(98.0, 100.0, trigger_bar(100.0))
    next_tick = 评估触发(98.0, 100.0, trigger_bar(100.01))
    assert equal["满足"] is False
    assert equal["前高突破价"] == 100.01
    assert next_tick["满足"] is True
    assert next_tick["限制条件"] == "上一根高点突破"


def test_reverse_above_previous_high_is_the_limiting_condition():
    below = 评估触发(105.0, 100.0, trigger_bar(104.99))
    touched = 评估触发(105.0, 100.0, trigger_bar(105.0))
    assert below["满足"] is False
    assert touched["满足"] is True
    assert touched["限制条件"] == "RSI反推价"


def test_reverse_price_is_rounded_up_to_valid_tick():
    below = 评估触发(105.003, 100.0, trigger_bar(105.0))
    touched = 评估触发(105.003, 100.0, trigger_bar(105.01))
    assert below["满足"] is False
    assert touched["满足"] is True
    assert abs(touched["最终买入触发价"] - 105.01) < 1e-9


def test_current_close_and_final_rsi_cannot_change_strict_trigger():
    first = 评估触发(98.0, 100.0, trigger_bar(100.01, close=10.0, rsi=1.0))
    second = 评估触发(98.0, 100.0, trigger_bar(100.01, close=999.0, rsi=99.0))
    assert first == second
