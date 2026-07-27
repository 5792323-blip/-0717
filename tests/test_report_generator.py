import os
import sys
import json

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
        "持仓过程": pd.DataFrame([
            {"K线索引": 3, "哨兵价": None, "本根触发哨兵价": None,
             "持仓数量": 0, "最终动作": "不交易", "动作原因": "尚未形成哨兵价"},
        ]),
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
    assert "本根实际检查哨兵价" in page
    assert "收盘后形成的下一根哨兵价" in page
    assert "RSI 信号贡献分析" in page
    assert "首次开仓的 RSI 信号归类" in page
    assert "const RSI_SIGNALS=['RSI上穿20','RSI上穿30','RSI上穿均线','RSI上穿70']" in page
    assert '"哨兵价": null' in page
    assert "allBarsMode" not in page
    assert "%%K线JSON%%" not in page
    assert "2024-01-03" in page


def test_non_positive_sentinel_values_are_rendered_as_empty(tmp_path):
    holding = pd.DataFrame([{
        "K线索引": 0, "日期": "2024-01-01", "哨兵价": 0,
        "哨兵价前值": 0, "本根触发哨兵价": 0,
        "最终买入触发价当前": 0, "最终动作": "不交易",
        "动作原因": "尚未形成哨兵价",
    }])
    result = {
        "股票代码": "000001", "交易明细": pd.DataFrame(),
        "持仓过程": holding, "初始资金": 100000,
        "最终现金": 100000, "配置快照": {},
    }
    source = pd.DataFrame([{
        "日期": "2024-01-01", "前复权_开盘": 10,
        "前复权_最高": 11, "前复权_最低": 9,
        "前复权_收盘": 10, "不复权_收盘": 10,
        "RSI_14": 50, "RSI_均线_20": 50, "ATR_14": 1,
    }])
    output = tmp_path / "empty-sentinel.html"
    生成报告(result, source, 输出路径=str(output))
    page = output.read_text(encoding="utf-8")
    start = page.index("KLINE=") + len("KLINE=")
    data, _ = json.JSONDecoder().raw_decode(page[start:])
    assert data[0]["哨兵价"] is None
    assert data[0]["本根触发哨兵价"] is None


def test_grid_addon_trade_gets_kline_index_for_replay_lines(tmp_path):
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    source = pd.DataFrame(
        {
            "前复权_开盘": [10] * 5, "前复权_最高": [11] * 5,
            "前复权_最低": [9] * 5, "前复权_收盘": [10] * 5,
            "不复权_开盘": [10] * 5, "不复权_最高": [11] * 5,
            "不复权_最低": [9] * 5, "不复权_收盘": [10] * 5,
            "RSI_14": [50] * 5, "RSI_均线_20": [50] * 5, "ATR_14": [1] * 5,
        },
        index=dates,
    )
    trades = pd.DataFrame([
        {"序号": 1, "持仓组ID": "G1", "网格级别": 0, "类型": "买入",
         "时间": "2024-01-02", "买入价": 10, "成交数量": 100},
        {"序号": 2, "持仓组ID": "G1", "网格级别": 1, "类型": "买入",
         "时间": "2024-01-03", "买入价": 9, "成交数量": 100,
         "信号类型": "网格加仓 L1"},
        {"序号": 3, "持仓组ID": "G1", "类型": "卖出",
         "时间": "2024-01-05", "卖出价": 11, "成交数量": 200,
         "卖出原因": "ATR退出", "盈亏比例": 0.1},
    ])
    holding = pd.DataFrame([
        {"K线索引": 0, "日期": "2024-01-01", "最终动作": "不交易", "持仓组ID": ""},
        {"K线索引": 1, "日期": "2024-01-02", "最终动作": "买入", "持仓组ID": "G1"},
        {"K线索引": 2, "日期": "2024-01-03", "最终动作": "加仓", "持仓组ID": "G1"},
        {"K线索引": 3, "日期": "2024-01-04", "最终动作": "不交易", "持仓组ID": "G1"},
        {"K线索引": 4, "日期": "2024-01-05", "最终动作": "卖出", "持仓组ID": "G1"},
    ])
    result = {"股票代码": "000001", "交易明细": trades, "持仓过程": holding,
              "初始资金": 100000, "最终现金": 102000, "买入次数": 2,
              "卖出次数": 1, "胜率": 100, "总收益率": 2,
              "配置快照": {}, "基准_个股买入持有": [100000] * 5,
              "基准_HS300": [100000] * 5}

    output = tmp_path / "grid-replay.html"
    生成报告(result, source, 输出路径=str(output))
    page = output.read_text(encoding="utf-8")

    assert '"信号类型": "网格加仓 L1"' in page
    assert '"K线索引": 2' in page
