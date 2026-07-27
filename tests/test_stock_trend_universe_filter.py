import importlib
from datetime import date, timedelta


module = importlib.import_module("8_过滤因子.stock_trend_universe_filter")


def _bar(date, close):
    return {"日期": date, "前复权_收盘": close}


def test_long_term_downtrend_blocks_new_entry():
    state = {}
    for index in range(150):
        day = date(2020, 1, 1) + timedelta(days=index)
        module.更新(_bar(day.isoformat(), 100 - index * 0.4), state, {})
    result = module.检查("RSI上穿30", {}, state, {})
    assert result["通过"] is False


def test_existing_position_is_exempt_from_universe_filter():
    state = {"已有持仓": True}
    result = module.检查("RSI上穿30", {}, state, {})
    assert result["通过"] is True
