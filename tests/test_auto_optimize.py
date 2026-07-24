import json
import os
import shutil

from 优化工具 import auto_optimize


def test_trial_config_searches_signal_and_filter_switches(tmp_path):
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "1_策略配置")
    target = tmp_path / "config"
    params = {
        "rsi_cross_20": False,
        "rsi_cross_30": True,
        "rsi_cross_ma": False,
        "rsi_cross_70": True,
        "启用RSI_MA过滤": False,
        "启用MA方向过滤": True,
        "RSI_MA检查K线数": 7,
        "MA对称斜率阈值": 1.2,
        "单笔买入上限比例": 0.12,
        "ATR倍数": 3.1,
    }
    auto_optimize.生成试验配置(base, str(target), params, 20_000_000)

    buy = auto_optimize.读取yaml(target / "买入信号配置.yaml")
    enabled = {item["英文标识"]: item["启用"] for item in buy["买入信号列表"]}
    assert enabled == {
        "rsi_cross_20": False,
        "rsi_cross_30": True,
        "rsi_cross_ma": False,
        "rsi_cross_70": True,
    }
    filters = auto_optimize.读取yaml(target / "过滤因子配置.yaml")
    by_name = {item["英文标识"]: item for item in filters["过滤因子列表"]}
    assert by_name["rsi_ma_filter"]["启用"] is False
    assert by_name["ma_direction_filter"]["启用"] is True
    assert by_name["ma_direction_filter"]["斜率下阈值"] == -1.2
    assert by_name["ma_direction_filter"]["斜率上阈值"] == 1.2

    original_cost = auto_optimize.配置交易成本指纹(base)
    assert auto_optimize.配置交易成本指纹(str(target)) == original_cost
