import importlib

import pandas as pd


factor = importlib.import_module("8_过滤因子.industry_boom_filter")


def _config(tmp_path):
    industries = tmp_path / "industries.csv"
    scores = tmp_path / "scores.csv"
    pd.DataFrame([
        {"股票代码": "600519", "生效日期": "2020-01-01", "行业名称": "食品饮料"},
        {"股票代码": "600519", "生效日期": "2021-01-01", "行业名称": "商贸零售"},
    ]).to_csv(industries, index=False)
    pd.DataFrame([
        {"行业名称": "食品饮料", "生效日期": "2020-01-01", "行业景气指数": 7.0},
        {"行业名称": "食品饮料", "生效日期": "2022-01-01", "行业景气指数": 4.0},
        {"行业名称": "商贸零售", "生效日期": "2021-01-01", "行业景气指数": 5.0},
    ]).to_csv(scores, index=False)
    return {"历史行业归属文件": str(industries), "历史行业评分文件": str(scores), "行业景气指数下限": 6.0}


def test_industry_boom_filter_uses_only_asof_industry_and_score(tmp_path):
    result = factor.检查("RSI上穿30", {"股票代码": "600519", "日期": "2020-06-01"}, {}, _config(tmp_path))
    assert result["通过"] is True
    assert result["行业名称"] == "食品饮料"
    assert result["行业评分生效日期"] == "2020-01-01"


def test_industry_boom_filter_blocks_missing_history_and_low_score(tmp_path):
    config = _config(tmp_path)
    missing = factor.检查("RSI上穿30", {"股票代码": "000001", "日期": "2020-06-01"}, {}, config)
    low = factor.检查("RSI上穿30", {"股票代码": "600519", "日期": "2021-06-01"}, {}, config)
    assert missing["通过"] is False
    assert missing["数据状态"] == "缺失"
    assert low["通过"] is False
    assert "不足" in low["原因"]


def test_industry_boom_filter_does_not_force_exit_existing_position(tmp_path):
    result = factor.检查("网格加仓 L1", {"股票代码": "600519", "日期": "2020-06-01"}, {"已有持仓": True}, _config(tmp_path))
    assert result["通过"] is True
    assert result["数据状态"] == "持仓豁免"
