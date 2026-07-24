import json
import re

import pandas as pd

from 回测引擎.report_generator import 生成报告
from 运行程序.interactive_backtest_app import (
    _构建组合实际交易,
    _构建组合实际持仓,
    _准备回放K线,
    生成多股策略回放页面,
)


def _raw_bars():
    times = pd.date_range("2024-01-02 10:00", periods=4, freq="60min")
    return pd.DataFrame({
        "完整时间": times.strftime("%Y-%m-%d %H:%M"),
        "日期": times.strftime("%Y-%m-%d"),
        "前复权_开盘": [10.0, 10.2, 10.5, 10.7],
        "前复权_最高": [10.3, 10.6, 10.8, 11.1],
        "前复权_最低": [9.9, 10.1, 10.4, 10.6],
        "前复权_收盘": [10.2, 10.5, 10.7, 11.0],
        "不复权_开盘": [10.0, 10.2, 10.5, 10.7],
        "不复权_最高": [10.3, 10.6, 10.8, 11.1],
        "不复权_最低": [9.9, 10.1, 10.4, 10.6],
        "不复权_收盘": [10.2, 10.5, 10.7, 11.0],
        "RSI_14": [25.0, 35.0, 45.0, 55.0],
        "RSI_均线_20": [30.0] * 4,
        "ATR_14": [0.2] * 4,
    })


def test_actual_audit_drives_trade_detail_arrows_and_real_times(tmp_path):
    raw = _raw_bars()
    audit = [
        {"时间": raw.iloc[1]["完整时间"], "股票代码": "688183", "类型": "买入", "结果": "实际成交", "成交股数": 200, "成交价": 10.5, "成交净额": 2101.0, "交易费用": 1.0, "K线索引": 1},
        {"时间": raw.iloc[3]["完整时间"], "股票代码": "688183", "类型": "卖出", "结果": "实际成交", "成交股数": 200, "成交价": 11.0, "成交净额": 2198.0, "交易费用": 2.0, "K线索引": 3},
    ]
    trades = _构建组合实际交易("688183", audit, raw)
    holding = pd.DataFrame({"K线索引": range(4), "日期": raw["日期"], "最终动作": ["等待"] * 4})
    state = _构建组合实际持仓(holding, raw, trades, audit, 300000)
    result = {
        "股票代码": "688183", "交易明细": trades, "持仓过程": state,
        "初始资金": 300000, "最终现金": 300097, "买入次数": 1,
        "卖出次数": 1, "胜率": 100.0, "总收益率": 0.0323,
        "配置快照": {}, "运行参数": {"组合实际回放": True},
    }
    output = tmp_path / "actual.html"
    生成报告(result, raw, 输出路径=str(output))
    page = output.read_text(encoding="utf-8")
    trade_payload = re.search(r"const TRADES=(.*?), KLINE=", page).group(1)
    kline_payload = re.search(r", KLINE=(.*?), EQUITY=", page).group(1)

    assert len(json.loads(trade_payload)) == 2
    assert [row["K线索引"] for row in json.loads(trade_payload)] == [1.0, 3.0]
    assert json.loads(kline_payload)[1]["完整时间"] == "2024-01-02 11:00"
    assert "组合实际成交明细" in page
    assert "renderPriceAccurate" in page
    assert "clippedHigh" in page


def test_legacy_portfolio_audit_still_populates_actual_table(tmp_path):
    summary = {
        "资金模式": "共享资金池网格", "资金审计": {"买入成交": 1},
        "组合初始资金": 1000000, "组合最终权益": 1000100,
        "组合成交明细": [
            {"股票代码": "688183", "类型": "买入", "结果": "实际成交", "成交股数": 200, "成交价": 10},
            {"股票代码": "688183", "类型": "卖出", "结果": "实际成交", "成交股数": 200, "成交价": 10.5},
        ],
    }
    details = [{"股票代码": "688183", "总收益率": 0.01, "最大回撤": 0.02}]
    form = {"portfolio_mode": "shared_grid", "capital": 1000000, "base_position": 300000}
    output = tmp_path / "multi.html"
    生成多股策略回放页面(output, "token", str(tmp_path), details, summary, form, [])
    page = output.read_text(encoding="utf-8")

    assert "<td>1/1</td>" in page
    assert "实际买/卖" in page
    assert "mainSplitter" in page
    assert "analysisToggle" in page


def test_replay_time_uses_datetime_index_when_full_time_is_missing():
    raw = _raw_bars().drop(columns=["完整时间"])
    raw.index = pd.date_range("2024-01-02 10:00", periods=4, freq="60min")
    holding = pd.DataFrame({"日期": ["2024-01-02", "2024-01-02"]})

    selected = _准备回放K线(raw, holding)

    assert selected["完整时间"].tolist() == [
        "2024-01-02 10:00", "2024-01-02 11:00",
        "2024-01-02 12:00", "2024-01-02 13:00",
    ]
