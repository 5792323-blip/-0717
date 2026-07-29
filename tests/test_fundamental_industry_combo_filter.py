import importlib


def test_combines_stock_and_industry_scores(tmp_path):
    module = importlib.import_module("8_过滤因子.fundamental_industry_combo_filter")
    stock = tmp_path / "stock.csv"
    stock.write_text(
        "股票代码,评分日期,总分,置信度,准入结论,硬风险\n600519,2026-04-01,80,1,基本面允许,\n",
        encoding="utf-8",
    )
    industry = tmp_path / "industry.csv"
    industry.write_text(
        "行业名称,生效日期,行业景气指数,覆盖权重\n食品饮料,2026-01-01,8,1\n",
        encoding="utf-8",
    )
    assignment = tmp_path / "assignment.csv"
    assignment.write_text(
        "股票代码,生效日期,行业名称\n600519,2020-01-01,食品饮料\n",
        encoding="utf-8",
    )
    result = module.检查("RSI上穿20", {"股票代码": "600519", "日期": "2026-05-01"}, {}, {
        "个股评分文件": str(stock), "行业评分文件": str(industry), "行业归属文件": str(assignment),
    })
    assert result["通过"]
    assert result["综合评分"] == 80


def test_missing_industry_score_blocks_new_entry(tmp_path):
    module = importlib.import_module("8_过滤因子.fundamental_industry_combo_filter")
    stock = tmp_path / "stock.csv"
    stock.write_text("股票代码,评分日期,总分,置信度,准入结论,硬风险\n600519,2026-04-01,80,1,基本面允许,\n", encoding="utf-8")
    assignment = tmp_path / "assignment.csv"
    assignment.write_text("股票代码,生效日期,行业名称\n600519,2020-01-01,食品饮料\n", encoding="utf-8")
    result = module.检查("RSI上穿20", {"股票代码": "600519", "日期": "2026-05-01"}, {}, {
        "个股评分文件": str(stock), "行业评分文件": str(tmp_path / "missing.csv"), "行业归属文件": str(assignment),
    })
    assert not result["通过"]
    assert result["数据状态"] == "缺失"
