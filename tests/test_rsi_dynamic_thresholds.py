import importlib


module = importlib.import_module("8_过滤因子.rsi_regime_adaptive_filter")


def test_fixed_mode_preserves_legacy_thresholds():
    state = {"rsi_regime_adaptive_filter": {"状态": "牛市"}}
    config = {"阈值模式": "fixed"}
    assert module.获取RSI阈值("RSI上穿20", state, config) == 20
    assert module.获取RSI阈值("RSI上穿70", state, config) == 70


def test_adaptive_mode_maps_thresholds_by_regime():
    state = {"rsi_regime_adaptive_filter": {"状态": "牛市"}}
    config = {
        "阈值模式": "adaptive",
        "状态阈值": {"牛市": {"RSI上穿20": 25, "RSI上穿70": 75}},
    }
    assert module.获取RSI阈值("RSI上穿20", state, config) == 25.0
    assert module.获取RSI阈值("RSI上穿70", state, config) == 75.0


def test_missing_regime_mapping_falls_back_to_fixed_value():
    state = {"rsi_regime_adaptive_filter": {"状态": "历史不足"}}
    config = {"阈值模式": "adaptive", "状态阈值": {"牛市": {"RSI上穿20": 25}}}
    assert module.获取RSI阈值("RSI上穿20", state, config) == 20


def test_signal_budget_defaults_are_legacy_neutral():
    import yaml

    with open("1_策略配置/买入信号配置.yaml", encoding="utf-8") as source:
        signals = yaml.safe_load(source)["买入信号列表"]
    assert [item["信号资金系数"] for item in signals] == [1.0, 1.0, 1.0, 1.0]
