import importlib.util
from pathlib import Path

import pandas as pd


path = Path(__file__).parents[1] / "基本面" / "导入申万历史行业归属.py"
spec = importlib.util.spec_from_file_location("sw_importer", path)
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


def test_importer_normalizes_source_and_requires_complete_mapping():
    raw = importer.标准化原始数据(pd.DataFrame([
        {"symbol": 1, "start_date": "2020-01-01", "industry_code": 480101, "update_time": "2024-01-01"},
        {"symbol": "600519", "start_date": "2020-01-01", "industry_code": "240101", "update_time": "2024-01-01"},
    ]))
    mapped, missing = importer.生成行业归属(raw, pd.DataFrame([{"行业代码": "480101", "行业名称": "银行"}]))
    assert raw["股票代码"].tolist() == ["000001", "600519"]
    assert mapped["行业代码"].tolist() == ["480101"]
    assert missing == ["240101"]


def test_importer_creates_backtest_rows_only_after_full_mapping():
    raw = importer.标准化原始数据(pd.DataFrame([
        {"symbol": "600519", "start_date": "2020-01-01", "industry_code": "240101", "update_time": "2024-01-01"},
    ]))
    mapped, missing = importer.生成行业归属(raw, pd.DataFrame([{"行业代码": "240101", "行业名称": "白酒"}]))
    assert missing == []
    assert mapped.loc[0, "行业名称"] == "白酒"
    assert mapped.loc[0, "分类标准"] == "申万行业分类"
