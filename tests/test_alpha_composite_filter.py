import importlib


filter_module = importlib.import_module("8_过滤因子.alpha_composite_filter")


def test_new_day_score_never_uses_current_day_close(monkeypatch):
    state = {}
    config = {"历史不足时放行": True}
    cache = {
        "模型": {"因子": [], "得分阈值": 0},
        "日线历史": [],
        "当前日": None,
        "当日K线": None,
        "得分": 1.25,
        "因子值": {},
    }
    monkeypatch.setattr(filter_module, "_加载模型", lambda *_: cache)
    monkeypatch.setattr(filter_module, "_完成日线", lambda value: None)

    filter_module.更新({
        "日期": "2024-01-02", "前复权_开盘": 10, "前复权_最高": 11,
        "前复权_最低": 9, "前复权_收盘": 10.5, "成交量": 100,
        "RSI_14": 40, "ATR_14": 1,
    }, state, config)

    assert cache["得分"] == 1.25
    assert filter_module.检查("RSI上穿20", {}, state, config)["通过"] is True


def test_score_must_be_strictly_greater_than_threshold(monkeypatch):
    state = {}
    cache = {"模型": {"得分阈值": 0}, "得分": 0.0, "因子值": {}}
    monkeypatch.setattr(filter_module, "_加载模型", lambda *_: cache)
    assert filter_module.检查("RSI上穿20", {}, state, {})["通过"] is False
