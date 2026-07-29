import csv

from 数据模块.历史成分股 import 读取历史成分股


def test_history_pool_uses_the_latest_snapshot_at_or_before_date(tmp_path):
    path = tmp_path / "hs300.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=["生效日期", "股票代码", "股票名称"])
        writer.writeheader()
        writer.writerows([
            {"生效日期": "2020-01-01", "股票代码": "sh.600000", "股票名称": "浦发银行"},
            {"生效日期": "2020-01-01", "股票代码": "SZ_000001", "股票名称": "平安银行"},
            {"生效日期": "2020-06-15", "股票代码": "SH_600000", "股票名称": "浦发银行"},
            {"生效日期": "2020-06-15", "股票代码": "SZ_000002", "股票名称": "万科A"},
        ])

    pool = 读取历史成分股(path)

    assert pool.包含("SH_600000", "2020-05-01")
    assert pool.包含("000001", "2020-05-01")
    assert not pool.包含("000001", "2020-06-15")
    assert pool.覆盖股票("2020-01-01", "2020-12-31") == ["000001", "000002", "600000"]
