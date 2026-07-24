import importlib


module = importlib.import_module("8_过滤因子.market_regime_filter")


def test_regime_uses_strictly_previous_index_date(monkeypatch):
    state = {"market_regime_filter": {
        "数据": __import__("pandas").DataFrame({
            "date": __import__("pandas").to_datetime(["2020-01-01", "2020-01-02"]),
            "close": [100, 50], "ma20": [90, 90], "ma60": [80, 80],
            "ma20_slope": [1, 1], "realized_vol": [0.01, 0.01],
            "vol_baseline": [0.01, 0.01],
        }), "状态": "历史不足", "明细": {}, "当前日期": None,
    }}
    config = {"防守模式允许信号": ["RSI上穿20"], "收缩模式允许信号": ["RSI上穿20"], "历史不足时放行": True}
    module.更新({"日期": "2020-01-02"}, state, config)
    assert state["market_regime_filter"]["明细"]["指数日期"] == "2020-01-01"


def test_defensive_regime_blocks_non_extreme_signal():
    state = {"market_regime_filter": {"数据": __import__("pandas").DataFrame(),
                                      "状态": "防守模式", "明细": {}}}
    config = {"防守模式允许信号": ["RSI上穿20"], "历史不足时放行": True}
    assert module.检查("RSI上穿20", {}, state, config)["通过"] is True
    assert module.检查("RSI上穿70", {}, state, config)["通过"] is False
