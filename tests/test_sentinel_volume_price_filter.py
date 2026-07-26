import importlib


因子 = importlib.import_module("8_过滤因子.sentinel_volume_price_filter")


def test_disabled_subfactors_only_record_without_blocking():
    config = {
        "启用项": {"收盘承接强度": True},
        "运行模式": "只记录",
        "最低收盘强度": 0.60,
    }
    result = 因子.检查(
        "RSI上穿30",
        {},
        {"哨兵量价快照": {
            "有效": True, "收盘强度": 0.2, "相对量能": 1.0,
            "缩量比例": 1.0, "近期价格变化": 0.01,
            "趋势涨幅": 0.01, "单根跌幅": 0.0,
            "上影比例": 0.1,
        }},
        config,
    )
    assert result["原始通过"] is False
    assert result["通过"] is True
    assert result["运行模式"] == "只记录"


def test_formal_mode_blocks_only_after_snapshot_check():
    config = {
        "启用项": {"收盘承接强度": True},
        "运行模式": "正式拦截",
        "最低收盘强度": 0.60,
    }
    result = 因子.检查(
        "RSI上穿20",
        {},
        {"哨兵量价快照": {
            "有效": True, "收盘强度": 0.2, "相对量能": 1.0,
            "缩量比例": 1.0, "近期价格变化": 0.01,
            "趋势涨幅": 0.01, "单根跌幅": 0.0,
            "上影比例": 0.1,
        }},
        config,
    )
    assert result["原始通过"] is False
    assert result["通过"] is False
