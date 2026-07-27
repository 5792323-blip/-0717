import importlib

import pandas as pd


factor = importlib.import_module("8_过滤因子.fundamental_universe_filter")


def _config():
    return {
        "PE相对行业倍数": 0.8,
        "ROE下限": 0.15,
        "近3年净利CAGR下限": 0.20,
        "资产负债率上限": 0.50,
        "经营现金流净利润比下限": 0.80,
        "行业景气指数下限": 0.0,
    }


def test_fundamental_filter_uses_latest_snapshot_not_future_snapshot(tmp_path):
    path = tmp_path / "fundamental.csv"
    pd.DataFrame([
        {"股票代码": "600519", "生效日期": "2020-01-01", "PE": 10, "行业PE": 20,
         "ROE": .2, "近3年净利CAGR": .25, "资产负债率": .4,
         "经营现金流净利润比": 1.0, "行业景气指数": .2},
        {"股票代码": "600519", "生效日期": "2024-01-01", "PE": 30, "行业PE": 20,
         "ROE": .2, "近3年净利CAGR": .25, "资产负债率": .4,
         "经营现金流净利润比": 1.0, "行业景气指数": .2},
    ]).to_csv(path, index=False)
    config = {**_config(), "历史数据文件": str(path)}
    result = factor.检查("RSI上穿30", {"股票代码": "600519", "日期": "2020-06-01"}, {}, config)
    assert result["通过"] is True
    assert result["生效日期"] == "2020-01-01"


def test_fundamental_filter_requires_all_five_factors(tmp_path):
    path = tmp_path / "fundamental.csv"
    pd.DataFrame([{
        "股票代码": "600519", "生效日期": "2020-01-01", "PE": 10, "行业PE": 20,
        "ROE": .10, "近3年净利CAGR": .25, "资产负债率": .4,
        "经营现金流净利润比": 1.0, "行业景气指数": .2,
    }]).to_csv(path, index=False)
    result = factor.检查(
        "RSI上穿30", {"股票代码": "600519", "日期": "2020-06-01"}, {},
        {**_config(), "历史数据文件": str(path)},
    )
    assert result["通过"] is False
    assert "ROE" in result["原因"]


def test_fundamental_filter_blocks_missing_history(tmp_path):
    result = factor.检查(
        "RSI上穿30", {"股票代码": "600519", "日期": "2020-06-01"}, {},
        {**_config(), "历史数据文件": str(tmp_path / "missing.csv")},
    )
    assert result["通过"] is False
    assert result["数据状态"] == "缺失"


def test_fundamental_filter_does_not_force_exit_existing_position():
    result = factor.检查(
        "网格加仓 L1", {"股票代码": "600519", "日期": "2020-06-01"},
        {"已有持仓": True}, _config(),
    )
    assert result["通过"] is True
    assert result["数据状态"] == "持仓豁免"
