import importlib

import numpy as np
import pandas as pd


module = importlib.import_module("分析工具.cross_sectional_exposure_attribution")


def test_rolling_beta_recovers_linear_market_exposure():
    index = pd.date_range("2020-01-01", periods=8)
    market = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02, 0.01, -0.03, 0.02], index=index)
    stock = 2.0 * market
    beta = module.计算滚动贝塔(stock, market, window=5, min_periods=5)
    assert np.isclose(beta.dropna().iloc[-1], 2.0)


def test_board_classification_is_deterministic_from_code_prefix():
    assert module.股票板块("688001") == "科创板"
    assert module.股票板块("300001") == "创业板"
    assert module.股票板块("600000") == "沪市主板"
    assert module.股票板块("000001") == "深市主板"


def test_exposure_group_boundaries():
    assert module.分组标签(0.2) == "低"
    assert module.分组标签(0.5) == "中"
    assert module.分组标签(0.9) == "高"


def test_residualization_removes_linear_exposure_component():
    index = pd.Index(range(6))
    exposure = pd.DataFrame({"beta": [1, 2, 3, 4, 5, 6]}, index=index)
    score = pd.Series([3, 5, 7, 9, 11, 13], index=index, dtype=float)
    residual = module.残差化(score, exposure)
    assert np.allclose(residual.to_numpy(), 0.0, atol=1e-10)
