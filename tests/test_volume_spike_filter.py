import importlib


module = importlib.import_module("8_过滤因子.volume_spike_filter")


def test_blocks_low_previous_day_turnover_ratio():
    result = module.检查(
        "RSI上穿20",
        {"_上一交易日成交额比20日均值": 0.69},
        {},
        {"最低成交额比率": 0.7, "历史不足时放行": True},
    )
    assert result["通过"] is False
    assert result["成交额比率"] == 0.69


def test_passes_equal_threshold():
    result = module.检查(
        "RSI上穿20",
        {"_上一交易日成交额比20日均值": 0.7},
        {},
        {"最低成交额比率": 0.7},
    )
    assert result["通过"] is True


def test_missing_history_follows_configuration():
    passed = module.检查("RSI上穿20", {}, {}, {"历史不足时放行": True})
    blocked = module.检查("RSI上穿20", {}, {}, {"历史不足时放行": False})
    assert passed["通过"] is True
    assert blocked["通过"] is False


def test_non_target_signal_is_not_filtered():
    result = module.检查(
        "RSI上穿均线",
        {"_上一交易日成交额比20日均值": 0.2},
        {},
        {"最低成交额比率": 0.7, "适用信号": ["RSI上穿30"]},
    )
    assert result["通过"] is True
