from 运行程序.interactive_backtest_app import 生成多股策略回放页面


def test_shared_account_report_populates_actual_trade_table(tmp_path):
    summary = {
        "资金模式": "共享账户",
        "资金审计": {"实际成交": 2},
        "组合初始资金": 1_000_000,
        "组合最终权益": 1_000_100,
        "组合成交明细": [
            {"股票代码": "688183", "类型": "买入", "结果": "实际成交", "成交股数": 200, "成交价": 10},
            {"股票代码": "688183", "类型": "卖出", "结果": "实际成交", "成交股数": 200, "成交价": 10.5},
        ],
        "组合股票汇总": {
            "688183": {
                "实际买入": 1, "实际卖出": 1, "组合拦截": 0,
                "期末股数": 0, "收益贡献率": 0.001,
            }
        },
    }
    details = [{"股票代码": "688183", "总收益率": 0.01, "最大回撤": 0.02}]
    form = {
        "portfolio_mode": "shared_grid", "capital": 1_000_000,
        "base_position": 300_000, "start": "2020-01-01", "end": "2026-03-31",
    }
    output = tmp_path / "multi.html"

    生成多股策略回放页面(output, "token", str(tmp_path), details, summary, form, [])
    page = output.read_text(encoding="utf-8")

    assert "<td>1/1</td>" in page
    assert "实际买/卖" in page
    assert "mainSplitter" in page
    assert "analysisToggle" not in page
    assert 'id="returnChartToggle"' not in page
    assert 'id="capitalChartToggle"' not in page
    assert 'id="returnChartPop"' not in page
    assert 'id="capitalChartPop"' not in page
    assert '<section class="analysis">' not in page
    assert "回测时间：2020-01-01 至 2026-03-31" in page
    assert "returnChartToggle').onclick" not in page
    assert "capitalChartToggle').onclick" not in page
    assert "document.querySelector('.analysis')" not in page
