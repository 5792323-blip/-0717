import os
import sys

import pandas as pd


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from 回测引擎.report_generator import 生成报告


def test_kline_replay_generates_pan_zoom_workbench(tmp_path):
    dates = pd.date_range("2024-01-01", periods=8, freq="D")
    source = pd.DataFrame(
        {
            "前复权_开盘": [10 + i for i in range(8)],
            "前复权_最高": [11 + i for i in range(8)],
            "前复权_最低": [9 + i for i in range(8)],
            "前复权_收盘": [10.5 + i for i in range(8)],
            "不复权_开盘": [10 + i for i in range(8)],
            "不复权_最高": [11 + i for i in range(8)],
            "不复权_最低": [9 + i for i in range(8)],
            "不复权_收盘": [10.5 + i for i in range(8)],
            "RSI_14": [50] * 8,
            "RSI_均线_20": [50] * 8,
            "ATR_14": [1] * 8,
        },
        index=dates,
    )
    trades = pd.DataFrame(
        [
            {"序号": 1, "类型": "买入", "时间": "2024-01-03 00:00", "买入价": 12.5, "仓位": 10000, "信号类型": "RSI上穿30"},
            {"序号": 1, "类型": "卖出", "时间": "2024-01-06 00:00", "卖出价": 15.5, "盈亏比例": 0.2, "卖出原因": "ATR退出"},
        ]
    )
    result = {
        "股票代码": "000001",
        "交易明细": trades,
        "持仓过程": pd.DataFrame(),
        "初始资金": 100000,
        "最终现金": 102000,
        "买入次数": 1,
        "卖出次数": 1,
        "胜率": 100,
        "总收益率": 2,
        "配置快照": {},
        "基准_个股买入持有": [100000 + i * 100 for i in range(8)],
        "基准_HS300": [100000 + i * 80 for i in range(8)],
    }

    output = tmp_path / "replay.html"
    生成报告(result, source, 输出路径=str(output))
    page = output.read_text(encoding="utf-8")

    assert "策略决策回放台" in page
    assert "个股收益（买入持有）" in page
    assert "策略超额个股" in page
    assert "滚轮缩放" in page
    assert "拖动左右浏览" in page
    assert "const tradePairs" in page
    assert "红线盈利" in page
    assert "绿线亏损" in page
    assert "allBarsMode" not in page
    assert "%%K线JSON%%" not in page
    assert "2024-01-03" in page
