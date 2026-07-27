import importlib

atr_protective_stop = importlib.import_module("6_卖出规则.atr_protective_stop")
fixed_stop_loss = importlib.import_module("6_卖出规则.fixed_stop_loss")
from 因子模块.grid_addon import 网格加仓


def test_atr_protective_stop_is_loss_side_only_by_price_threshold():
    assert not atr_protective_stop.检查(0.01, 3, 100, ATR倍数=2.0)["触发"]
    assert atr_protective_stop.检查(-0.06, 3, 100, ATR倍数=2.0)["触发"]


def test_fixed_stop_loss_uses_explicit_percentage():
    assert not fixed_stop_loss.检查(-0.079, 100, 固定止损比例=0.08)["触发"]
    assert fixed_stop_loss.检查(-0.08, 100, 固定止损比例=0.08)["触发"]


def test_grid_risk_limits_are_opt_in():
    position = {
        "买入时间": 0,
        "网格_最近加仓索引": 0,
        "网格_已触发次数": 0,
        "网格_首笔股数": 100,
        "网格_基准最高价": 100,
    }
    bar = {"前复权_最低": 90}
    factor = 网格加仓({"最大加仓次数": 2, "首次回撤阈值": 0.05})
    assert factor.加仓前检查(position, bar, {"当前索引": 1})["触发加仓"]


def test_grid_risk_limits_block_short_interval_and_old_position():
    position = {
        "买入时间": 0,
        "网格_最近加仓索引": 0,
        "网格_已触发次数": 0,
        "网格_首笔股数": 100,
        "网格_基准最高价": 100,
    }
    bar = {"前复权_最低": 90}
    factor = 网格加仓({
        "最大加仓次数": 2,
        "首次回撤阈值": 0.05,
        "启用风控限制": True,
        "最小加仓间隔K线": 5,
        "禁止加仓持仓K线数": 30,
    })
    assert not factor.加仓前检查(position, bar, {"当前索引": 1})["触发加仓"]
    assert not factor.加仓前检查(position, bar, {"当前索引": 30})["触发加仓"]
