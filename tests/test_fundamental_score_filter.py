import importlib


def test_score_filter_uses_asof_score_and_exempts_existing_position(tmp_path):
    factor = importlib.import_module("8_过滤因子.fundamental_score_filter")
    path = tmp_path / "scores.csv"
    path.write_text(
        "股票代码,评分日期,总分,置信度,硬风险\n600519,2026-01-01,70,0.5,\n"
        "600519,2026-07-28,50,0.5,\n", encoding="utf-8"
    )
    config = {"个股评分文件": str(path), "最低总分": 65, "最低置信度": .25}
    result = factor.检查("RSI上穿30", {"股票代码": "600519", "日期": "2026-03-01"}, {}, config)
    assert result["通过"] is True
    result = factor.检查("RSI上穿30", {"股票代码": "600519", "日期": "2026-08-01"}, {}, config)
    assert result["通过"] is False
    result = factor.检查("网格加仓 L1", {"股票代码": "600519", "日期": "2026-08-01"}, {"已有持仓": True}, config)
    assert result["通过"] is True
