import importlib

from 策略引擎.规则执行器 import 规则执行器


SNAPSHOT = {
    "有效": True,
    "相对量能": 1.0,
    "缩量比例": 1.0,
    "近期价格变化": 0.01,
    "趋势涨幅": 0.01,
    "收盘强度": 0.20,
    "上影比例": 0.10,
    "单根跌幅": 0.0,
}


def test_close_strength_is_an_independent_formal_entry_gate():
    factor = importlib.import_module("8_过滤因子.sentinel_close_strength_filter")

    result = factor.检查(
        "RSI上穿30", {}, {"哨兵量价快照": SNAPSHOT}, {"最低收盘强度": 0.60}
    )

    assert result["通过"] is False
    assert "拦截" in result["原因"]


def test_upper_shadow_respects_signal_scope():
    factor = importlib.import_module("8_过滤因子.sentinel_upper_shadow_filter")
    snapshot = {**SNAPSHOT, "上影比例": 0.80}

    result = factor.检查(
        "RSI上穿70", {}, {"哨兵量价快照": snapshot},
        {"最大上影比例": 0.35, "适用信号": ["RSI上穿20"]},
    )

    assert result["通过"] is True
    assert result["适用"] is False


def test_volume_drop_blocks_only_the_defined_risk_pattern():
    factor = importlib.import_module("8_过滤因子.sentinel_volume_drop_filter")
    snapshot = {**SNAPSHOT, "单根跌幅": -0.03, "相对量能": 1.80, "收盘强度": 0.20}

    result = factor.检查("RSI上穿20", {}, {"哨兵量价快照": snapshot}, {})

    assert result["通过"] is False


def test_entry_structure_group_allows_any_enabled_confirmation_to_pass():
    class AlwaysFail:
        @staticmethod
        def 检查(*_args):
            return {"通过": False, "原因": "不满足缩量结构"}

    class AlwaysPass:
        @staticmethod
        def 检查(*_args):
            return {"通过": True, "原因": "满足量价转强"}

    executor = object.__new__(规则执行器)
    executor.过滤因子列表 = [
        {"名称": "sentinel_volume_dryup_filter", "模块": AlwaysFail, "配置": {
            "名称": "缩量回撤衰竭", "组合组": "sentinel_entry_structure", "组合逻辑": "任一通过",
        }},
        {"名称": "sentinel_volume_price_strength_filter", "模块": AlwaysPass, "配置": {
            "名称": "量价转强确认", "组合组": "sentinel_entry_structure", "组合逻辑": "任一通过",
        }},
    ]

    result = executor._检查过滤因子("RSI上穿30", {}, {})

    assert result["允许买入"] is True
    assert all(item["组合通过"] is True for item in result["明细"])
