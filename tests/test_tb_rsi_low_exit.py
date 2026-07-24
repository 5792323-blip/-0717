import importlib


module = importlib.import_module("6_卖出规则.tb_rsi_low_exit")


def test_triggers_when_low_rsi_crosses_down_threshold():
    result = module.检查(上一根最低价RSI=72, 当前最低价RSI=68, 下穿阈值=[70, 30, 20])
    assert result["触发"] is True
    assert result["卖出比例"] == 1.0
    assert result["RSI阈值"] == 70


def test_does_not_trigger_without_down_cross():
    assert module.检查(上一根最低价RSI=68, 当前最低价RSI=66, 下穿阈值=[70])["触发"] is False
    assert module.检查(上一根最低价RSI=72, 当前最低价RSI=71, 下穿阈值=[70])["触发"] is False
