import numpy as np

from 买入执行模块.rsi_reverse_price import 计算, 计算SMA_RSI
from 策略引擎.反推因子 import 从价格算RSI
from 策略引擎.rsi import 计算RSI


def test_reverse_price_uses_13_known_changes_plus_unknown_price():
    prices = [100, 101, 99, 100, 102, 101, 103, 102, 104, 103, 102, 101, 100, 99, 98]
    result = 计算(prices, 50)

    assert result["可用"] is True
    assert result["RSI算法"] == "SMA"
    assert np.isclose(
        从价格算RSI(prices[1:] + [result["RSI反推价"]]), 50.0, atol=1e-2
    )


def test_reverse_price_has_same_formula_for_close_high_and_low_sources():
    for prices in (
        [100, 101, 99, 100, 102, 101, 103, 102, 104, 103, 102, 101, 100, 99, 98],
        [110, 111, 109, 112, 113, 111, 114, 113, 115, 114, 113, 112, 111, 110, 109],
        [90, 91, 89, 92, 93, 91, 94, 93, 95, 94, 93, 92, 91, 90, 89],
    ):
        result = 计算(prices, 30)
        assert result["可用"] is True
        assert np.isclose(
            从价格算RSI(prices[1:] + [result["RSI反推价"]]), 30.0, atol=1e-2
        )


def test_sma_rsi_reverse_matches_formal_rsi_last_value():
    prices = [100, 101, 99, 100, 102, 101, 103, 102, 104, 103, 102, 101, 100, 99, 98, 100]
    formal = 计算RSI(prices, 周期=14).iloc[-1]
    assert np.isclose(计算SMA_RSI(prices), formal, atol=1e-12)


def test_reverse_price_rejects_insufficient_history():
    assert 计算([1, 2, 3, 4, 5], 20)["可用"] is False
