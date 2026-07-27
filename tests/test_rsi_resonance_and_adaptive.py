import importlib


resonance = importlib.import_module("8_过滤因子.rsi_resonance_filter")
adaptive = importlib.import_module("8_过滤因子.rsi_regime_adaptive_filter")


def _bar(date, close, high=None, low=None, volume=100):
    return {
        "日期": date, "前复权_收盘": close,
        "前复权_最高": high if high is not None else close + 1,
        "前复权_最低": low if low is not None else close - 1,
        "成交量": volume,
    }


def test_resonance_requires_two_confirmations_and_records_details():
    state = {"rsi_resonance_filter": {
        "指标": {"MACD多头": True, "KDJ多头": False, "量比": 1.2},
        "样本数": 40,
    }}
    result = resonance.检查("RSI上穿30", {}, state, {
        "最少通过数量": 2, "要求成交量确认": True, "最低量比": 1.0,
    })
    assert result["通过"] is True
    assert result["共振明细"]["MACD"] is True
    assert result["共振明细"]["成交量"] is True


def test_resonance_blocks_when_history_is_insufficient():
    result = resonance.检查("RSI上穿30", {}, {}, {"历史不足时放行": False})
    assert result["通过"] is False


def test_adaptive_filter_changes_allowed_signals_by_regime():
    state = {"rsi_regime_adaptive_filter": {"状态": "熊市"}}
    config = {"熊市允许信号": ["RSI上穿20", "RSI上穿30"]}
    assert adaptive.检查("RSI上穿30", {}, state, config)["通过"] is True
    assert adaptive.检查("RSI上穿70", {}, state, config)["通过"] is False


def test_adaptive_update_uses_completed_bars_before_classifying():
    state = {}
    config = {"短均线周期": 3, "长均线周期": 5}
    for index in range(10):
        adaptive.更新(_bar(f"2020-01-{index + 1:02d}", 100 + index), state, config)
    assert adaptive.获取状态(state, config)["状态"] == "牛市"
