import importlib

import pandas as pd


module = importlib.import_module("8_过滤因子.index_trend_filter")


def make_state():
    data = pd.DataFrame({
        "date": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"]),
        "close": [100.0, 110.0, 90.0],
        "trend_ma": [None, 105.0, 100.0],
    })
    return {"index_trend_filter": {2: {"数据": data, "状态": "历史不足", "明细": {}}}}


def test_uses_only_completed_previous_index_day():
    state = make_state()
    config = {"均线周期": 2, "历史不足时放行": True}
    module.更新({"日期": "2020-01-03"}, state, config)
    result = module.检查("RSI上穿20", {}, state, config)
    assert result["通过"] is True
    assert result["状态明细"]["指数日期"] == "2020-01-02"


def test_blocks_when_previous_close_is_below_ma():
    state = make_state()
    config = {"均线周期": 2}
    module.更新({"日期": "2020-01-04"}, state, config)
    result = module.检查("RSI上穿20", {}, state, config)
    assert result["通过"] is False


def test_missing_history_follows_configuration():
    state = make_state()
    config = {"均线周期": 2, "历史不足时放行": False}
    module.更新({"日期": "2020-01-02"}, state, config)
    assert module.检查("RSI上穿20", {}, state, config)["通过"] is False
