import pandas as pd
import pytest
import re

from 组合回测.统一多股执行器 import _写入股票归因过程, _股票归因
from 运行程序 import interactive_backtest_app as app_module
from 运行程序.interactive_backtest_app import 生成多股策略回放页面
from 运行程序.run_backtest import 单股摘要
from 回测引擎.report_generator import 生成报告


def _trades(rows):
    return pd.DataFrame(rows).fillna(0)


def test_partial_fill_attribution_uses_actual_quantity_and_single_fee():
    trades = _trades([
        {"时间": "2025-01-02", "execution_id": "X1", "类型": "买入", "成交数量": 100,
         "总成本": 1_005.0, "交易费用": 5.0},
        {"时间": "2025-01-03", "execution_id": "X2", "类型": "卖出", "成交数量": 40,
         "卖出净金额": 438.0, "交易费用": 2.0},
    ])

    result = _股票归因(trades, ending_value=660.0)

    # 买入总成本已含一次 5 元费用；卖出净额已扣一次 2 元费用。
    assert result["持仓数量"] == 60
    assert result["持仓成本"] == pytest.approx(603.0)
    assert result["已实现损益"] == pytest.approx(36.0)
    assert result["未实现损益"] == pytest.approx(57.0)
    assert result["累计损益贡献"] == pytest.approx(93.0)


def test_reopen_after_flat_keeps_realized_pnl_and_new_lot_unrealized_pnl():
    trades = _trades([
        {"时间": "2025-01-02", "execution_id": "X1", "类型": "买入", "成交数量": 100,
         "总成本": 1_005.0},
        {"时间": "2025-01-03", "execution_id": "X2", "类型": "卖出", "成交数量": 100,
         "卖出净金额": 1_098.0},
        {"时间": "2025-01-04", "execution_id": "X3", "类型": "买入", "成交数量": 200,
         "总成本": 1_810.0},
    ])

    result = _股票归因(trades, ending_value=1_760.0)

    assert result["持仓数量"] == 200
    assert result["持仓成本"] == pytest.approx(1_810.0)
    assert result["已实现损益"] == pytest.approx(93.0)
    assert result["未实现损益"] == pytest.approx(-50.0)
    assert result["累计损益贡献"] == pytest.approx(43.0)


def test_two_simultaneous_stock_contributions_reconcile_without_cash_allocation():
    first = _股票归因(_trades([
        {"时间": "2025-01-02", "execution_id": "X1", "类型": "买入", "成交数量": 100,
         "总成本": 1_005.0},
    ]), ending_value=1_050.0)
    second = _股票归因(_trades([
        {"时间": "2025-01-02", "execution_id": "X2", "类型": "买入", "成交数量": 200,
         "总成本": 2_005.0},
    ]), ending_value=1_950.0)

    portfolio_initial = 10_000.0
    portfolio_cash = portfolio_initial - 1_005.0 - 2_005.0
    portfolio_equity = portfolio_cash + 1_050.0 + 1_950.0

    assert first["累计损益贡献"] == pytest.approx(45.0)
    assert second["累计损益贡献"] == pytest.approx(-55.0)
    assert first["累计损益贡献"] + second["累计损益贡献"] == pytest.approx(
        portfolio_equity - portfolio_initial
    )


def test_stock_process_contains_attribution_not_shared_cash_or_equity():
    process = pd.DataFrame([
        {"时间": "2025-01-02", "持仓市值": 1_000.0, "当前现金": 99_000.0, "权益": 100_000.0},
        {"时间": "2025-01-03", "持仓市值": 1_050.0, "当前现金": 99_000.0, "权益": 100_050.0},
    ])
    trades = _trades([
        {"时间": "2025-01-02", "execution_id": "X1", "类型": "买入", "成交数量": 100,
         "总成本": 1_005.0},
    ])

    attributed = _写入股票归因过程(process, trades)

    assert attributed.loc[1, "持仓成本"] == pytest.approx(1_005.0)
    assert attributed.loc[1, "累计损益贡献"] == pytest.approx(45.0)
    assert attributed["当前现金"].isna().all()
    assert attributed["权益"].isna().all()


def test_shared_page_uses_stock_contribution_fields_not_total_return(tmp_path):
    summary = {
        "资金模式": "共享账户", "组合初始资金": 200_000,
        "组合最终权益": 199_000, "组合总收益率": -0.005,
        "组合股票汇总": {
            "600118": {"实际买入": 1, "实际卖出": 1, "拒绝数": 0,
                        "期末股数": 0, "损益贡献": -1_000, "收益贡献率": -0.005},
            "600519": {"实际买入": 0, "实际卖出": 0, "拒绝数": 26,
                        "期末股数": 0, "损益贡献": 0, "收益贡献率": 0},
        },
    }
    details = [
        {"股票代码": "600118", "股票级不可用": True, "总收益率": None, "最大回撤": None},
        {"股票代码": "600519", "股票级不可用": True, "总收益率": None, "最大回撤": None},
    ]
    form = {"portfolio_mode": "shared_grid", "capital": 200_000, "base_position": 100_000,
            "start": "2025-01-01", "end": "2025-03-31"}
    output = tmp_path / "multi.html"

    生成多股策略回放页面(output, "token", str(tmp_path), details, summary, form, [])
    page = output.read_text(encoding="utf-8")

    assert "损益贡献" in page
    assert "收益贡献率" in page
    assert "策略收益" not in page
    assert "<td>0/0</td>" in page
    assert "<td>26</td>" in page
    assert "+0.00%" in page


def test_shared_page_values_are_sourced_from_saved_stock_summary(tmp_path):
    summary = {
        "资金模式": "共享账户", "组合初始资金": 200_000,
        "组合最终权益": 201_000, "组合总收益率": 0.005,
        "组合股票汇总": {
            "600118": {"实际买入": 2, "实际卖出": 1, "拒绝数": 3,
                        "期末股数": 100, "损益贡献": 1_234.56, "收益贡献率": 0.0061728},
        },
    }
    details = [{"股票代码": "600118", "股票级不可用": True, "总收益率": None, "最大回撤": None}]
    form = {"portfolio_mode": "shared_grid", "capital": 200_000, "base_position": 100_000,
            "start": "2025-01-01", "end": "2025-03-31"}
    output = tmp_path / "multi.html"
    生成多股策略回放页面(output, "token", str(tmp_path), details, summary, form, [])
    page = output.read_text(encoding="utf-8")
    assert "1,234.56" in page
    assert "+0.62%" in page
    assert "2/1" in page
    assert ">3<" in page


def test_cli_shared_stock_summary_does_not_coerce_unavailable_account_metrics_to_zero():
    raw = pd.DataFrame({"日期": ["2025-01-02", "2025-01-03"]})
    summary = 单股摘要({
        "股票代码": "600519", "原始K线数据": raw, "股票级不可用": True,
        "买入次数": 0, "卖出次数": 0, "实际成交数": 0, "拒绝数": 26,
        "期末股数": 100, "期末持仓市值": 2_500,
        "累计损益贡献": 0, "收益贡献率": 0,
    }, "2025-01-01", "2025-03-31")

    assert summary["最终现金"] is None
    assert summary["最终权益"] is None
    assert summary["总收益率"] is None
    assert summary["期末股数"] == 100
    assert summary["期末持仓市值"] == pytest.approx(2_500)
    assert summary["累计损益贡献"] == 0
    assert summary["拒绝数"] == 26


def test_stock_replay_marks_shared_stock_cash_and_equity_as_unavailable(tmp_path):
    raw = pd.DataFrame({
        "完整时间": ["2025-01-02 15:00"], "日期": ["2025-01-02"],
        "前复权_收盘": [10.0], "不复权_收盘": [10.0], "RSI_14": [50.0],
    })
    holding = pd.DataFrame({"K线索引": [0], "权益": [None], "当前现金": [None]})
    output = tmp_path / "stock.html"

    生成报告({
        "股票代码": "600519", "股票级不可用": True, "初始资金": 200_000,
        "总收益率": None, "收益贡献率": -0.00842320295,
        "交易明细": pd.DataFrame(), "持仓过程": holding,
        "运行参数": {"组合实际回放": True, "股票归因": True},
    }, raw, 输出路径=output)
    page = output.read_text(encoding="utf-8")

    assert "共享账户股票归因（无股票级权益）" in page
    assert "股票级现金不可用" in page
    assert "组合级" in page
    assert "EQUITY=[]" in page
    value = float(re.search(r"ATTRIBUTION_RETURN=([-0-9.]+)", page).group(1))
    assert value == pytest.approx(-0.842320295)


def test_shared_stock_replay_route_injects_actual_attribution_return(tmp_path):
    stock_dir = tmp_path / "股票" / "600118"
    stock_dir.mkdir(parents=True)
    pd.DataFrame({
        "完整时间": ["2025-01-02 15:00"], "日期": ["2025-01-02"],
        "前复权_开盘": [10.0], "前复权_最高": [10.1], "前复权_最低": [9.9],
        "前复权_收盘": [10.0], "不复权_开盘": [10.0], "不复权_最高": [10.1],
        "不复权_最低": [9.9], "不复权_收盘": [10.0], "RSI_14": [50.0],
    }).to_csv(stock_dir / "回放行情.csv.gz", index=False, compression="gzip")
    pd.DataFrame(columns=["时间", "类型", "成交数量"]).to_csv(
        stock_dir / "交易明细.csv", index=False
    )
    pd.DataFrame({"K线索引": [0], "权益": [None], "当前现金": [None], "反推哨兵价列表": ["[]"]}).to_csv(
        stock_dir / "持仓过程.csv", index=False
    )
    (stock_dir / "股票归因.json").write_text(
        '{"股票代码":"600118","初始资金":200000,"股票级不可用":true,"收益贡献率":-0.00842320295}',
        encoding="utf-8",
    )
    previous = dict(app_module.最近多股报告)
    app_module.最近多股报告.update({"token": "attribution", "run_dir": str(tmp_path), "path": None})
    try:
        response = app_module.应用.test_client().get("/multi/attribution/stock/600118")
        page = response.get_data(as_text=True)
    finally:
        app_module.最近多股报告.clear()
        app_module.最近多股报告.update(previous)

    assert response.status_code == 200
    assert "收益贡献率" in page
    value = float(re.search(r"ATTRIBUTION_RETURN=([-0-9.]+)", page).group(1))
    assert value == pytest.approx(-0.842320295)
    assert "ATTRIBUTION_RETURN!==null" in page
    assert "EQUITY=[]" in page
