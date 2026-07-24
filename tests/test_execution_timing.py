import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from 策略引擎.规则执行器 import 规则执行器


def make_bar(**overrides):
    data = {
        "前复权_开盘": 100.0,
        "前复权_最高": 105.0,
        "前复权_最低": 95.0,
        "前复权_收盘": 102.0,
        "不复权_开盘": 100.0,
        "不复权_最高": 105.0,
        "不复权_最低": 95.0,
        "不复权_收盘": 102.0,
        "成交量": 1000,
        "ATR_14": 2.0,
        "RSI_14": 35.0,
        "RSI_均线_20": 30.0,
        "股票代码": "600519",
    }
    data.update(overrides)
    return pd.Series(data)


def make_executor():
    executor = object.__new__(规则执行器)
    executor.上一根_最高价 = 100.0
    executor.上一根_最低价 = 95.0
    executor.上一根_不复权收盘 = 100.0
    executor.上一根_ATR = 2.0
    executor.上一根_RSI_MA = 30.0
    executor._上上根RSI = 18.0
    executor.哨兵价当前 = None
    executor.哨兵价已形成 = False
    executor.哨兵价形成类型 = None
    executor.哨兵价锁定信号类型 = None
    executor.哨兵价形成索引 = None
    executor.哨兵价本根新形成 = False
    executor.哨兵价已确认可执行 = True
    executor.价格序列 = list(range(1, 17))
    executor.MA序列 = []
    executor.买入规则列表 = [{
        "类型": "RSI上穿20",
        "确认K线数": 0,
        "需要均线上涨确认": False,
    }]
    executor.本根决策 = {"动作原因": "", "决策记录": {}}
    return executor


def test_reverse_price_window_excludes_current_close():
    executor = make_executor()
    current = make_bar(RSI_14=25.0, _上一根RSI=18.0, 前复权_收盘=999.0)
    captured = {}

    def fake_reverse(window, **kwargs):
        captured["window"] = list(window)
        captured["target"] = kwargs["目标RSI"]
        return {"目标价位": 110.0}

    with patch("买入执行模块.rsi_reverse_price.反推RSI价位", side_effect=fake_reverse):
        executor._计算哨兵价(current, 16)

    assert captured["window"] == list(range(1, 16))
    assert 999.0 not in captured["window"]
    assert executor.哨兵价当前 == 110.0


def test_no_sentinel_when_rsi_still_below_threshold():
    executor = make_executor()
    current = make_bar(RSI_14=18.8, _上一根RSI=15.7, 前复权_最高=1186.97)
    with patch("买入执行模块.rsi_reverse_price.反推RSI价位", return_value={"目标价位": 1190.80}) as reverse:
        executor._计算哨兵价(current, 16)
    reverse.assert_not_called()
    assert executor.哨兵价当前 is None
    assert executor.哨兵价形成类型 is None
    assert executor.哨兵价已形成 is False


def test_real_rsi_30_cross_replaces_pending_ma_sentinel():
    executor = make_executor()
    executor.上一根_RSI_MA = 67.4
    executor.上一根_最高价 = 35.32
    executor.哨兵价当前 = 46.27
    executor.哨兵价已形成 = True
    executor.哨兵价形成类型 = "RSI上穿均线"
    executor.待确认哨兵价 = 46.27
    executor.待确认哨兵价类型 = "RSI上穿均线"
    current = make_bar(
        RSI_14=34.73,
        _上一根RSI=24.54,
        前复权_最高=36.05,
    )

    with patch("买入执行模块.rsi_reverse_price.反推RSI价位", return_value={"目标价位": 45.51}) as reverse:
        executor._计算哨兵价(current, 66)

    assert reverse.call_args.kwargs["目标RSI"] == 30
    assert executor.哨兵价形成类型 == "RSI上穿30"
    assert executor.哨兵价当前 == 45.51
    assert executor.待确认哨兵价 is None
    assert executor.哨兵价已确认可执行 is True


def test_existing_sentinel_does_not_move_downward_in_tracking():
    executor = make_executor()
    executor.哨兵价当前 = 20.0
    executor.哨兵价已形成 = True
    executor.RSI反推价当前 = 15.0
    executor.上一根突破基准价当前 = 10.0

    executor._更新哨兵价跟踪(make_bar(前复权_最高=17.0))

    assert executor.哨兵价当前 == 20.0
    assert executor.上一根突破基准价当前 == 10.0


def test_new_cross_can_create_lower_sentinel_than_previous_one():
    executor = make_executor()
    executor.哨兵价当前 = 20.0
    executor.哨兵价已形成 = True
    executor.哨兵价形成类型 = "RSI上穿20"
    executor.上一根突破基准价当前 = 20.0
    executor.上一根_RSI_MA = 35.0
    executor.价格序列 = list(range(1, 17))

    current = make_bar(RSI_14=31.0, _上一根RSI=29.0, 前复权_最高=17.0)

    with patch("策略引擎.规则执行器.计算RSI反推价", return_value={"RSI反推价": 16.0}):
        executor._计算哨兵价(current, 16)

    assert executor.哨兵价当前 == 17.0
    assert executor.RSI反推价当前 == 16.0
    assert executor.哨兵价形成类型 == "RSI上穿30"
    assert executor.哨兵价本根新形成 is True


def test_strict_breakout_requires_next_valid_price_above_previous_high():
    executor = make_executor()
    executor.哨兵价当前 = 105.0
    executor.RSI反推价当前 = 105.0
    executor.上一根突破基准价当前 = 100.0
    executor.哨兵价已形成 = True
    executor.哨兵价形成类型 = "RSI上穿20"
    executor.哨兵价形成索引 = 10
    executor.哨兵价已确认可执行 = True
    executor.哨兵价本根新形成 = False
    executor.最大总持仓数 = 10
    executor.当前持仓 = {}
    executor.本根决策 = {"买入信号": [], "过滤检查": [], "决策记录": {}, "动作原因": ""}
    executor.过滤因子列表 = []
    executor.信号质量对照 = {}
    executor.连续亏损次数 = 0
    executor.冷却期剩余K线 = 0
    executor.有底背离 = False
    executor.有顶背离 = False
    executor.基础单只金额 = 10000
    executor.最大单只比例 = 1.0
    executor.最大总仓位比例 = 1.0
    executor.现金底线比例 = 0.0
    executor.已买入K线数 = 1
    executor.当前现金 = 100000.0
    executor.买入规则列表 = [{"类型": "RSI上穿20", "基础质量分": 1.0, "单笔买入上限": 10000}]
    executor.因子管理器 = None
    executor.预测器 = None
    executor._执行买入 = lambda **kwargs: True

    executor.RSI反推价当前 = 98.0
    executor.上一根突破基准价当前 = 105.0
    executor._检查买入(make_bar(前复权_最高=105.01, 不复权_最高=105.01), 20)

    assert executor.本根决策["买入信号"][0]["价格突破"] is True
    assert executor.本根决策["买入信号"][0]["满足"] is True


def test_non_tradable_bars_are_blocked():
    executor = make_executor()
    assert executor._行情不可交易(make_bar(成交量=0)) is True
    assert executor._行情不可交易(make_bar(前复权_收盘=None)) is True
    assert executor._行情不可交易(make_bar(不复权_开盘=0)) is True
    assert executor._行情不可交易(make_bar()) is False


def test_sealed_limit_up_blocks_buy_but_unsealed_touch_does_not():
    executor = make_executor()
    executor.涨跌停比例 = 0.10
    sealed = make_bar(不复权_开盘=110.0, 不复权_最高=110.0,
                      不复权_最低=110.0, 不复权_收盘=110.0)
    touched = make_bar(不复权_开盘=105.0, 不复权_最高=110.0,
                       不复权_最低=104.0, 不复权_收盘=106.0)
    assert executor._封死涨停(sealed) is True
    assert executor._封死涨停(touched) is False


def test_sealed_limit_down_blocks_sell():
    executor = make_executor()
    executor.涨跌停比例 = 0.10
    sealed = make_bar(不复权_开盘=90.0, 不复权_最高=90.0,
                      不复权_最低=90.0, 不复权_收盘=90.0)
    assert executor._封死跌停(sealed) is True


def test_limit_ratio_uses_market_and_date():
    executor = make_executor()
    executor.涨跌停比例 = 0.10
    assert executor._获取涨跌停比例(make_bar(股票代码="600519", 日期="2024-01-01")) == 0.10
    assert executor._获取涨跌停比例(make_bar(股票代码="688001", 日期="2024-01-01")) == 0.20
    assert executor._获取涨跌停比例(make_bar(股票代码="300001", 日期="2020-08-21")) == 0.10
    assert executor._获取涨跌停比例(make_bar(股票代码="300001", 日期="2020-08-24")) == 0.20


def test_gap_up_uses_open_price_and_non_breakout_does_not_buy():
    executor = make_executor()
    executor.哨兵价当前 = 105.0
    executor.RSI反推价当前 = 105.0
    executor.上一根突破基准价当前 = 100.0
    executor.哨兵价已形成 = True
    executor.哨兵价形成类型 = "RSI上穿20"
    executor.哨兵价形成索引 = 10
    executor.最大总持仓数 = 10
    executor.当前持仓 = {}
    executor.本根决策 = {"买入信号": [], "过滤检查": [], "决策记录": {}, "动作原因": ""}
    executor.过滤因子列表 = []
    executor.信号质量对照 = {}
    executor.连续亏损次数 = 0
    executor.冷却期剩余K线 = 0
    executor.有底背离 = False
    executor.有顶背离 = False
    executor.基础单只金额 = 10000
    executor.最大单只比例 = 1.0
    executor.最大总仓位比例 = 1.0
    executor.现金底线比例 = 0.0
    executor.当前现金 = 100000.0
    executor.买入规则列表 = [{"类型": "RSI上穿20", "基础质量分": 1.0, "单笔买入上限": 10000}]
    executor.因子管理器 = None
    executor.预测器 = None
    calls = []
    executor._执行买入 = lambda **kwargs: calls.append(kwargs) or True

    executor._检查买入(make_bar(前复权_开盘=110.0, 前复权_最高=112.0,
                                不复权_开盘=110.0, 不复权_最高=112.0), 20)
    assert len(calls) == 1
    assert calls[0]["哨兵价"] == 105.0

    calls.clear()
    executor.本根决策 = {"买入信号": [], "过滤检查": [], "决策记录": {}, "动作原因": ""}
    executor._检查买入(make_bar(前复权_最高=104.99), 21)
    assert calls == []


def test_single_lot_overrides_signal_amount_limit():
    executor = make_executor()
    executor.买入溢价 = 1.0
    executor.佣金率 = 0.0
    executor.过户费率 = 0.0
    executor.当前持仓 = {}
    executor.当前现金 = 500000.0
    executor.已买入K线数 = 1
    executor.基础单只金额 = 200000.0
    executor.最大单只比例 = 1.0
    executor.最大总仓位比例 = 1.0
    executor.现金底线比例 = 0.0
    executor.哨兵价形成类型 = "RSI上穿20"
    executor.交易记录器 = SimpleNamespace(
        记录信号K线=lambda **kwargs: None,
        设置哨兵价=lambda value: None,
        记录买入=lambda **kwargs: None,
        更新交易记录=lambda *args, **kwargs: None,
        买入序号=1,
    )
    executor.预测器 = None
    executor.因子管理器 = None
    executor._执行买入 = executor._执行买入
    executor._获取买入规则 = lambda signal: {
        "类型": signal, "单笔买入上限": 200000.0, "基础质量分": 1.0
    }
    executor.本根决策 = {"决策记录": {"买入": {}}}

    assert executor._执行买入(
        规则=None,
        K线数据=make_bar(前复权_开盘=2750.0, 前复权_最高=2800.0, 前复权_最低=2700.0,
                            不复权_开盘=2750.0, 不复权_最高=2800.0, 不复权_最低=2700.0),
        当前索引=1,
        当前RSI=25.0,
        哨兵价=2700.0,
        信号类型="RSI上穿20",
        信号质量分=1.0,
    ) is True
    assert executor.当前持仓["600519"]["股数"] == 100


def test_sell_rule_uses_previous_completed_close():
    executor = make_executor()
    executor.已买入K线数 = 2
    executor.当前持仓 = {"600519": {"买入时间": 0, "买入价": 100.0, "成本": 10000.0,
                                  "总成本": 10000.0, "股数": 100, "最高价": 110.0,
                                  "RSI峰值": 60.0}}
    executor.滑点 = 0.0
    executor.佣金率 = 0.0
    executor.印花税率 = 0.0
    executor.过户费率 = 0.0
    executor.本根决策 = {"决策记录": {"卖出": {}}, "卖出检查": []}
    executor.因子管理器 = None
    executor.卖出规则列表 = [{
        "名称": "capture",
        "说明": "capture",
        "配置": {},
        "模块": SimpleNamespace(检查=lambda **kwargs: {
            "触发": False,
            "原因": str(kwargs["持仓盈亏比例"]),
        }),
    }]
    executor.价格序列 = []
    executor.交易记录器 = SimpleNamespace(更新RSI峰值=lambda value: None)

    executor._检查卖出(executor.当前持仓["600519"], make_bar(不复权_收盘=999.0), 2, "600519")
    reason = executor.本根决策["卖出检查"][0]["原因"]
    assert "0.0" not in reason
