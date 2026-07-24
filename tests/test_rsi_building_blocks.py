import os
import shutil

import pandas as pd
import yaml

from 运行程序.interactive_backtest_app import 应用表单到配置, 构建默认表单, 提取模式配置
from 策略引擎.rsi_source import 准备RSI指标


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "1_策略配置")


def 测试数据():
    return pd.DataFrame({
        "前复权_最高": [10, 11, 12, 13, 14, 15],
        "前复权_收盘": [10, 10, 11, 11, 12, 12],
        "前复权_最低": [10, 9, 8, 7, 6, 5],
    })


def test_three_rsi_modules_are_calculated_and_selected():
    high = 准备RSI指标(测试数据(), "high", RSI周期=2, 均线周期=2)
    low = 准备RSI指标(测试数据(), "low", RSI周期=2, 均线周期=2)
    assert {"RSI_最高价", "RSI_收盘价", "RSI_最低价"}.issubset(high.columns)
    pd.testing.assert_series_equal(high["RSI_14"], high["RSI_最高价"], check_names=False)
    pd.testing.assert_series_equal(low["RSI_14"], low["RSI_最低价"], check_names=False)
    assert high["RSI_14"].iloc[-1] > low["RSI_14"].iloc[-1]


def test_page_parameters_write_to_experiment_snapshot(tmp_path):
    snapshot = tmp_path / "config"
    shutil.copytree(CONFIG, snapshot)
    form = 构建默认表单()
    form["single_rsi_price_source"] = "high"
    form["single_entry_timing"] = "close_confirm_next_open"
    应用表单到配置(snapshot, 提取模式配置(form, "single"))
    parameters = yaml.safe_load((snapshot / "参数配置.yaml").read_text(encoding="utf-8"))
    assert parameters["技术指标参数"]["RSI价格源"] == "high"
    assert parameters["买入参数"]["买入时机模式"] == "close_confirm_next_open"
