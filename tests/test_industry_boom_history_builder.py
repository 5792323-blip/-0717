import importlib.util
from pathlib import Path

import pandas as pd


path = Path(__file__).parents[1] / "基本面" / "构建行业景气历史评分.py"
spec = importlib.util.spec_from_file_location("boom_builder", path)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_confirmed_source_replaces_public_observation_at_same_time():
    ledger = pd.DataFrame([{"指标键": "银行|息差", "行业": "银行", "建议权重": 1.0}])
    history = pd.DataFrame([
        {"指标键": "银行|息差", "生效日期": "2020-01-31", "数据截止日": "2020-01-30", "指标评分": 4, "来源优先级": 10},
        {"指标键": "银行|息差", "生效日期": "2020-01-31", "数据截止日": "2020-01-31", "指标评分": 7, "来源优先级": 100},
    ])
    result = builder.构建(ledger, history)
    assert result.loc[0, "行业景气指数"] == 7
