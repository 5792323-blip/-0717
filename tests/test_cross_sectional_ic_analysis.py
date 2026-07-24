import pandas as pd

from 分析工具 import cross_sectional_ic_analysis as module


def test_cross_sectional_ic_is_positive_for_monotonic_future_returns():
    group = pd.DataFrame({
        "momentum_20": range(20),
        "reversal_5": range(20),
        "low_volatility_20": range(20),
        "liquidity_20": range(20),
        "forward_5": range(20),
    })
    result = module.计算日期截面(group, "20日动量", minimum_assets=20)
    assert result["IC"] > 0.99
    assert result["多空收益差"] > 0


def test_cross_sectional_ic_rejects_small_universe():
    group = pd.DataFrame({
        "momentum_20": range(10), "reversal_5": range(10),
        "low_volatility_20": range(10), "liquidity_20": range(10),
        "forward_5": range(10),
    })
    assert module.计算日期截面(group, "20日动量", minimum_assets=20) is None
