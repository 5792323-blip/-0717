import csv
from pathlib import Path

from 组合回测.共享资金池网格 import replay


def _write_stock(root, stock, events):
    directory = root / stock
    directory.mkdir()
    fields = ["类型", "时间", "买入价", "卖出价", "成交数量", "信号类型", "信号质量分", "网格级别"]
    with (directory / "交易明细.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(events)

    with (directory / "持仓过程.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["日期", "不复权收盘"])
        writer.writeheader()
        for event in events:
            writer.writerow({"日期": event["时间"], "不复权收盘": event.get("买入价") or event.get("卖出价")})


def test_same_timestamp_candidates_are_ranked_before_cash_is_allocated(tmp_path):
    _write_stock(tmp_path, "000001", [{
        "类型": "买入", "时间": "2023-01-01", "买入价": 10, "卖出价": "",
        "成交数量": 100, "信号类型": "RSI上穿20", "信号质量分": 0.5, "网格级别": 0,
    }])
    _write_stock(tmp_path, "000002", [{
        "类型": "买入", "时间": "2023-01-01", "买入价": 10, "卖出价": "",
        "成交数量": 100, "信号类型": "RSI上穿30", "信号质量分": 1.0, "网格级别": 0,
    }])

    details = [{"股票代码": stock, "结果目录": str(tmp_path / stock)} for stock in ("000001", "000002")]
    result = replay(details, 100000, max_positions=2, max_total_ratio=1.0,
                    cash_floor=0.0, max_daily_buy_ratio=0.12, stock_capital=30000)

    actual = [row for row in result["组合成交明细"] if row["结果"] == "实际成交"]
    assert len(actual) == 2
    assert actual[0]["股票代码"] == "000002"
    assert actual[0]["候选队列序号"] == 1
    assert actual[1]["成交股数"] < actual[0]["成交股数"]
    assert result["资金审计"]["候选队列信号数"] == 2


def test_target_position_allocates_three_grid_layers(tmp_path):
    events = [
        {"类型": "买入", "时间": "2023-01-01", "买入价": 10, "卖出价": "", "成交数量": 100, "信号类型": "RSI上穿20", "信号质量分": 1.0, "网格级别": 0},
        {"类型": "买入", "时间": "2023-01-02", "买入价": 10, "卖出价": "", "成交数量": 100, "信号类型": "网格加仓", "信号质量分": 1.0, "网格级别": 1},
        {"类型": "买入", "时间": "2023-01-03", "买入价": 10, "卖出价": "", "成交数量": 100, "信号类型": "网格加仓", "信号质量分": 1.0, "网格级别": 2},
    ]
    _write_stock(tmp_path, "000001", events)
    result = replay([{"股票代码": "000001", "结果目录": str(tmp_path / "000001")}], 100000,
                    max_positions=1, max_total_ratio=1.0, cash_floor=0.0,
                    max_daily_buy_ratio=1.0, stock_capital=30000)

    actual = [row for row in result["组合成交明细"] if row["结果"] == "实际成交"]
    assert [row["成交股数"] for row in actual] == [700, 800, 700]
    assert result["最大使用资金"] == 22000
