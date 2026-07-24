import importlib


module = importlib.import_module("6_卖出规则.stagnation_exit")


def test_triggers_after_four_bars_without_minimum_mfe_while_losing():
    result = module.检查(
        -0.01,
        持有K线数=4,
        最高价=100.4,
        前复权买入价=100.0,
        检查K线数=4,
        最低MFE=0.005,
    )
    assert result["触发"] is True


def test_does_not_trigger_when_mfe_reached():
    result = module.检查(
        -0.01,
        持有K线数=4,
        最高价=100.5,
        前复权买入价=100.0,
        检查K线数=4,
        最低MFE=0.005,
    )
    assert result["触发"] is False


def test_does_not_trigger_profitable_or_early_trade():
    assert not module.检查(
        0.001, 持有K线数=4, 最高价=100.1, 前复权买入价=100.0
    )["触发"]
    assert not module.检查(
        -0.01, 持有K线数=3, 最高价=100.1, 前复权买入价=100.0
    )["触发"]
