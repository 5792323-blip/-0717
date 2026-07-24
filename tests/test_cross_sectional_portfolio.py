import importlib

import pandas as pd


module = importlib.import_module("组合回测.横截面组合")


def test_daily_aggregation_uses_first_open_last_close_and_sum_amount():
    bars = pd.DataFrame({
        "日期": ["2020-01-02", "2020-01-02"],
        "前复权_开盘": [10.0, 10.5],
        "前复权_最高": [11.0, 12.0],
        "前复权_最低": [9.0, 10.0],
        "前复权_收盘": [10.5, 11.5],
        "成交额": [100.0, 200.0],
    })
    daily = module.聚合日线(bars)
    assert daily.iloc[0]["open"] == 10.0
    assert daily.iloc[0]["close"] == 11.5
    assert daily.iloc[0]["high"] == 12.0
    assert daily.iloc[0]["amount"] == 300.0


def test_sell_cost_includes_stamp_tax_but_buy_does_not():
    costs = {"佣金": 0.00025, "印花税": 0.001, "过户费": 0.00001, "滑点": 0.001}
    buy = module.交易费用(100_000, "买入", costs)
    sell = module.交易费用(100_000, "卖出", costs)
    assert sell - buy == 100.0


def test_selection_uses_explicit_previous_signal_date():
    dates = pd.to_datetime(["2020-01-01", "2020-01-02"])
    features = {}
    for column in ["momentum_20", "reversal_5", "low_volatility_20", "liquidity_20"]:
        features[column] = pd.DataFrame(
            {"A": [2.0, 0.0], "B": [1.0, 3.0]}, index=dates
        )
    opens = pd.DataFrame({"A": [10.0, 10.0], "B": [10.0, 10.0]}, index=dates)
    selected, _ = module.选择股票(
        features, dates[0], dates[1], ["A", "B"], "20日动量", 1, opens
    )
    assert selected == ["A"]


def test_twenty_day_reversal_selects_low_momentum_stock():
    dates = pd.to_datetime(["2020-01-01", "2020-01-02"])
    features = {
        column: pd.DataFrame({"A": [2.0, 0.0], "B": [1.0, 3.0]}, index=dates)
        for column in ["momentum_20", "reversal_5", "low_volatility_20", "liquidity_20"]
    }
    opens = pd.DataFrame({"A": [10.0, 10.0], "B": [10.0, 10.0]}, index=dates)
    selected, _ = module.选择股票(
        features, dates[0], dates[1], ["A", "B"], "20日反转", 1, opens
    )
    assert selected == ["B"]


def test_market_risk_off_liquidates_at_next_rebalance():
    dates = pd.date_range("2020-01-01", periods=12, freq="D")
    daily = pd.DataFrame({
        "open": 10.0, "close": 10.0, "momentum_20": 1.0,
        "reversal_5": 1.0, "low_volatility_20": 1.0, "liquidity_20": 1.0,
    }, index=dates)
    regime = pd.Series(True, index=dates)
    regime.loc[dates[9]:] = False
    costs = {"佣金": 0.0, "印花税": 0.0, "过户费": 0.0, "滑点": 0.0}
    result = module.运行组合(
        {"A": daily}, ["A"], "20日动量", dates[0], dates[-1], costs,
        initial_capital=1_000_000, top_k=1, market_regime=regime,
    )
    trades = result["交易明细"]
    assert trades["方向"].tolist() == ["买入", "卖出"]
    assert result["权益曲线"].iloc[-1]["持仓数"] == 0


def test_rank_buffer_retains_incumbent_outside_entry_top_k():
    scores = pd.Series({"A": 0.9, "B": 0.8, "C": 0.7, "D": 0.6})
    selected = module.构建缓冲目标(
        scores, {"C": 100}, top_k=2, retain_rank=3
    )
    assert selected == ["C", "A"]


def test_replacement_limit_keeps_enough_incumbents():
    scores = pd.Series({"N1": 1.0, "N2": 0.9, "A": 0.8, "B": 0.7, "C": 0.6})
    selected = module.构建缓冲目标(
        scores, {"A": 100, "B": 100, "C": 100}, top_k=3,
        retain_rank=3, max_replacements=1,
    )
    assert sum(stock in {"A", "B", "C"} for stock in selected) == 2
    assert selected == ["A", "B", "N1"]
