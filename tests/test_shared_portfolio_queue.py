import csv

from 组合回测.共享资金池网格 import replay


def _stock(root, code, rows):
    directory = root / code
    directory.mkdir()
    fields = ["类型", "时间", "买入价", "卖出价", "成交数量", "信号类型", "信号质量分", "网格级别"]
    with (directory / "交易明细.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with (directory / "持仓过程.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["日期", "不复权收盘"])
        writer.writeheader()
        for row in rows:
            writer.writerow({"日期": row["时间"], "不复权收盘": row.get("买入价") or row.get("卖出价")})


def test_full_position_signal_enters_queue_then_executes_after_exit(tmp_path):
    _stock(tmp_path, "000001", [
        {"类型": "买入", "时间": "2023-01-01", "买入价": 10, "卖出价": "", "成交数量": 100,
         "信号类型": "RSI上穿20", "信号质量分": 1, "网格级别": 0},
        {"类型": "卖出", "时间": "2023-01-02", "买入价": "", "卖出价": 10, "成交数量": 1000,
         "信号类型": "止盈", "信号质量分": 0, "网格级别": 0},
    ])
    _stock(tmp_path, "000002", [
        {"类型": "买入", "时间": "2023-01-01", "买入价": 20, "卖出价": "", "成交数量": 100,
         "信号类型": "RSI上穿30", "信号质量分": 1, "网格级别": 0},
    ])
    details = [{"股票代码": code, "结果目录": str(tmp_path / code)} for code in ("000001", "000002")]
    result = replay(details, 100000, max_positions=1, max_total_ratio=1,
                    cash_floor=0, max_daily_buy_ratio=1, stock_capital=10000)
    assert result["资金审计"]["候选队列进入"] == 1
    assert result["资金审计"]["候选队列成交"] == 1


def test_expired_candidate_is_not_executed(tmp_path):
    _stock(tmp_path, "000001", [{
        "类型": "买入", "时间": "2023-01-01", "买入价": 10, "卖出价": "", "成交数量": 100,
        "信号类型": "RSI上穿20", "信号质量分": 1, "网格级别": 0,
    }])
    _stock(tmp_path, "000002", [{
        "类型": "买入", "时间": "2023-01-01", "买入价": 20, "卖出价": "", "成交数量": 100,
        "信号类型": "RSI上穿30", "信号质量分": 1, "网格级别": 0,
    }])
    details = [{"股票代码": code, "结果目录": str(tmp_path / code)} for code in ("000001", "000002")]
    result = replay(details, 100000, max_positions=1, max_total_ratio=1,
                    cash_floor=0, max_daily_buy_ratio=1, stock_capital=10000,
                    candidate_expiry_bars=0)
    assert result["资金审计"].get("候选队列成交", 0) == 0
