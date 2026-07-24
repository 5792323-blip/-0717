import importlib


模块 = importlib.import_module("6_卖出规则.rsi_threshold_hold")


def test_fixed_threshold_holds_until_rsi_crosses_back_below():
    state = 模块.更新({}, 28, 31, 25)
    assert state["守仓中"] is True
    assert state["阈值名称"] == "RSI上穿30"
    assert 模块.应暂缓(state, "atr_trailing", ["atr_trailing"]) is True

    still_holding = 模块.更新(state, 31, 30, 25)
    assert still_holding["守仓中"] is True

    released = 模块.更新(still_holding, 30, 29.9, 25)
    assert released["守仓中"] is False
    assert 模块.应暂缓(released, "atr_trailing", ["atr_trailing"]) is False


def test_highest_crossed_threshold_wins_and_ma_can_guard():
    high_cross = 模块.更新({}, 65, 82, 60)
    assert high_cross["阈值名称"] == "RSI上穿80"

    ma_cross = 模块.更新({}, 42, 48, 45)
    assert ma_cross["守仓中"] is True
    assert ma_cross["阈值名称"] == "RSI上穿均线"
    assert ma_cross["阈值"] == 45
