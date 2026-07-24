import importlib


def test_rsi_guard_builds_atr_buffered_guard_price():
    check = importlib.import_module("6_卖出规则.rsi_guard").检查
    result = check(当前ATR=2, 买入价=100, 最高价=115, RSI峰值=82, 当前RSI=75)
    assert result["触发"] is True
    assert result["止损价"] == 114


def test_rsi_guard_requires_high_level_cross():
    check = importlib.import_module("6_卖出规则.rsi_guard").检查
    assert check(当前ATR=2, 买入价=100, RSI峰值=75, 当前RSI=72)["触发"] is False


def test_divergence_fix_is_independently_callable():
    check = importlib.import_module("6_卖出规则.divergence_fix").检查
    assert check(有顶背离=True)["触发"] is True
    bottom = check(有底背离=True, 底背离暂缓K线数=3)
    assert bottom["触发"] is False
    assert bottom["暂缓K线数"] == 3
