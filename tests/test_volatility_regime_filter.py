import importlib


module = importlib.import_module("8_过滤因子.volatility_regime_filter")


def bar(date, close):
    return {
        "日期": date, "前复权_开盘": close, "前复权_最高": close,
        "前复权_最低": close, "前复权_收盘": close, "成交量": 100,
    }


def test_high_volatility_allows_only_configured_signal():
    state = {}
    config = {"计算周期": 20, "高波动阈值": 0.03, "低波动阈值": 0.001,
              "高波动允许信号": ["RSI上穿20"], "历史不足时放行": True}
    prices = [100, 110, 90, 115, 88, 120, 85, 118, 86, 121, 84, 119, 83]
    for index, price in enumerate(prices):
        module.更新(bar(f"2020-01-{index + 1:02d}", price), state, config)
    assert state["volatility_regime_filter"]["分类"] == "高波动"
    assert module.检查("RSI上穿20", {}, state, config)["通过"] is True
    assert module.检查("RSI上穿70", {}, state, config)["通过"] is False


def test_current_day_updates_do_not_change_completed_day_regime():
    state = {}
    config = {"计算周期": 4, "高波动阈值": 0.03, "低波动阈值": 0.001,
              "高波动允许信号": ["RSI上穿20"], "历史不足时放行": True}
    for index, price in enumerate([100, 101, 99, 100, 101, 100]):
        module.更新(bar(f"2020-01-{index + 1:02d}", price), state, config)
    previous = dict(state["volatility_regime_filter"])
    module.更新(bar("2020-01-07", 1000), state, config)
    assert state["volatility_regime_filter"]["分类"] == previous["分类"]
