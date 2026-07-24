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
    assert [row["成交股数"] for row in actual] == [700, 700, 700]
    assert result["最大使用资金"] == 21000


def test_fixed_tranche_mode_uses_equal_allocation_layers(tmp_path):
    events = [
        {"类型": "买入", "时间": f"2023-01-0{index}", "买入价": 10, "卖出价": "", "成交数量": 100,
         "信号类型": "网格加仓", "信号质量分": 1.0, "网格级别": index - 1}
        for index in range(1, 4)
    ]
    _write_stock(tmp_path, "000001", events)
    result = replay([{"股票代码": "000001", "结果目录": str(tmp_path / "000001")}], 100000,
                    max_positions=1, max_total_ratio=1.0, cash_floor=0.0,
                    max_daily_buy_ratio=1.0, stock_capital=10000,
                    grid_mode="fixed_tranche", initial_position_ratio=0.25,
                    followup_position_ratio=0.25)
    actual = [row for row in result["组合成交明细"] if row["结果"] == "实际成交"]
    assert [row["成交股数"] for row in actual] == [200, 200, 200]


def test_multiplier_mode_uses_geometric_allocation_layers(tmp_path):
    events = [
        {"类型": "买入", "时间": f"2023-01-0{index}", "买入价": 10, "卖出价": "", "成交数量": 100,
         "信号类型": "网格加仓", "信号质量分": 1.0, "网格级别": index - 1}
        for index in range(1, 4)
    ]
    _write_stock(tmp_path, "000001", events)
    result = replay([{"股票代码": "000001", "结果目录": str(tmp_path / "000001")}], 100000,
                    max_positions=1, max_total_ratio=1.0, cash_floor=0.0,
                    max_daily_buy_ratio=1.0, stock_capital=10000,
                    grid_mode="multiplier", initial_position_ratio=0.25,
                    grid_multiplier=2.0)
    actual = [row for row in result["组合成交明细"] if row["结果"] == "实际成交"]
    assert [row["成交股数"] for row in actual] == [200, 400, 800]


def test_linear_mode_uses_one_two_three_initial_share_units(tmp_path):
    events = [
        {"类型": "买入", "时间": f"2023-01-0{index}", "买入价": 10, "卖出价": "", "成交数量": 100,
         "信号类型": "网格加仓", "信号质量分": 1.0, "网格级别": index - 1}
        for index in range(1, 4)
    ]
    _write_stock(tmp_path, "000001", events)
    result = replay([{"股票代码": "000001", "结果目录": str(tmp_path / "000001")}], 100000,
                    max_positions=1, max_total_ratio=1.0, cash_floor=0.0,
                    max_daily_buy_ratio=1.0, stock_capital=10000,
                    grid_mode="linear", initial_position_ratio=0.25)
    actual = [row for row in result["组合成交明细"] if row["结果"] == "实际成交"]
    assert [row["成交股数"] for row in actual] == [200, 400, 600]


def test_initial_position_uses_one_lot_when_budget_is_below_normal_lot_value(tmp_path):
    _write_stock(tmp_path, "000001", [{
        "类型": "买入", "时间": "2023-01-01", "买入价": 300, "卖出价": "",
        "成交数量": 100, "信号类型": "RSI上穿20", "信号质量分": 1.0, "网格级别": 0,
    }])
    result = replay([{"股票代码": "000001", "结果目录": str(tmp_path / "000001")}], 100000,
                    max_positions=1, max_total_ratio=1.0, cash_floor=0.0,
                    max_daily_buy_ratio=1.0, stock_capital=100000,
                    initial_position_ratio=0.25)
    actual = [row for row in result["组合成交明细"] if row["结果"] == "实际成交"]
    assert [row["成交股数"] for row in actual] == [100]


def test_initial_position_uses_two_hundred_shares_for_star_market(tmp_path):
    _write_stock(tmp_path, "688001", [{
        "类型": "买入", "时间": "2023-01-01", "买入价": 200, "卖出价": "",
        "成交数量": 200, "信号类型": "RSI上穿20", "信号质量分": 1.0, "网格级别": 0,
    }])
    result = replay([{"股票代码": "688001", "结果目录": str(tmp_path / "688001")}], 100000,
                    max_positions=1, max_total_ratio=1.0, cash_floor=0.0,
                    max_daily_buy_ratio=1.0, stock_capital=100000,
                    initial_position_ratio=0.25)
    actual = [row for row in result["组合成交明细"] if row["结果"] == "实际成交"]
    assert [row["成交股数"] for row in actual] == [200]


def test_initial_position_uses_three_hundred_shares_for_bse_market(tmp_path):
    _write_stock(tmp_path, "830001", [{
        "类型": "买入", "时间": "2023-01-01", "买入价": 100, "卖出价": "",
        "成交数量": 300, "信号类型": "RSI上穿20", "信号质量分": 1.0, "网格级别": 0,
    }])
    result = replay([{"股票代码": "830001", "结果目录": str(tmp_path / "830001")}], 100000,
                    max_positions=1, max_total_ratio=1.0, cash_floor=0.0,
                    max_daily_buy_ratio=1.0, stock_capital=100000,
                    initial_position_ratio=0.25)
    actual = [row for row in result["组合成交明细"] if row["结果"] == "实际成交"]
    assert [row["成交股数"] for row in actual] == [300]


def test_grid_addon_uses_target_shares_even_when_cash_is_insufficient(tmp_path):
    _write_stock(tmp_path, "000001", [
        {"类型": "买入", "时间": "2023-01-01", "买入价": 1000, "卖出价": "",
         "成交数量": 100, "信号类型": "RSI上穿20", "信号质量分": 1.0, "网格级别": 0},
        {"类型": "买入", "时间": "2023-01-02", "买入价": 1000, "卖出价": "",
         "成交数量": 100, "信号类型": "网格加仓", "信号质量分": 1.0, "网格级别": 1},
    ])
    result = replay([{"股票代码": "000001", "结果目录": str(tmp_path / "000001")}], 110000,
                    max_positions=1, max_total_ratio=1.0, cash_floor=0.0,
                    max_daily_buy_ratio=1.0, stock_capital=100000,
                    initial_position_ratio=0.25)
    actual = [row for row in result["组合成交明细"] if row["结果"] == "实际成交"]
    assert [row["成交股数"] for row in actual] == [100, 100]
    assert result["资金审计"]["网格加仓成交"] == 1
    assert result["组合权益曲线"][-1]["现金"] < 0
