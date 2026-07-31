import json

import pandas as pd
import pytest

from 数据模块.数据质量审计 import 审计行情, 生成数据版本
from 运行程序.结果生命周期 import 清理可重建深度数据, 预览清理, 锁定


def test_行情审计拒绝不合理_ohlc和重复日期(tmp_path):
    frame = pd.DataFrame([
        {"日期": "2025-01-01", "前复权_开盘": 10, "前复权_最高": 9,
         "前复权_最低": 8, "前复权_收盘": 10, "不复权_开盘": 10,
         "不复权_最高": 10, "不复权_最低": 8, "不复权_收盘": 10},
        {"日期": "2025-01-01", "前复权_开盘": 10, "前复权_最高": 11,
         "前复权_最低": 9, "前复权_收盘": 10, "不复权_开盘": 10,
         "不复权_最高": 11, "不复权_最低": 9, "不复权_收盘": 10},
    ])
    report = 审计行情(frame)
    assert report["status"] == "FAIL"
    assert report["duplicate_dates"] == 1
    assert report["bad_ohlc"] == 1


def test_数据版本包含行情和基准内容(tmp_path):
    stock = tmp_path / "600519_双价格合并.pkl"
    benchmark = tmp_path / "hs300_日K线.pkl"
    pd.DataFrame({"日期": ["2025-01-01"]}).to_pickle(stock)
    pd.DataFrame({"date": ["2025-01-01"], "close": [1]}).to_pickle(benchmark)
    first = 生成数据版本([stock], [benchmark])
    stock.write_bytes(stock.read_bytes() + b"x")
    second = 生成数据版本([stock], [benchmark])
    assert first["hash"] != second["hash"]
    assert second["files"] == 2


def test_清理先返回预览且锁定后失败(tmp_path):
    (tmp_path / "运行清单.json").write_text(json.dumps({"run_id": "r", "locked": False}), encoding="utf-8")
    (tmp_path / "回放行情.csv.gz").write_text("x", encoding="utf-8")
    preview = 预览清理(tmp_path)
    assert preview["删除数量"] == 1
    assert (tmp_path / "回放行情.csv.gz").exists()
    锁定(tmp_path)
    with pytest.raises(PermissionError):
        清理可重建深度数据(tmp_path, confirm=True)
