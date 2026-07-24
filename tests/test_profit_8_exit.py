import importlib


module = importlib.import_module("6_卖出规则.profit_8_exit")


def test_triggers_when_profit_reaches_eight_percent():
    result = module.检查(0.081)
    assert result["触发"] is True
    assert result["卖出比例"] == 1.0


def test_does_not_trigger_below_threshold_or_missing_profit():
    assert module.检查(0.079)["触发"] is False
    assert module.检查(None)["触发"] is False


def test_threshold_can_be_adjusted_by_config():
    assert module.检查(0.061, 盈利阈值=0.06)["触发"] is True
