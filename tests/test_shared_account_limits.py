import os
import shutil

import pytest
import yaml

from 回测引擎.backtest_engine import 准备回测数据
from 策略引擎.交易账户 import 交易账户
import 组合回测.统一多股执行器 as multi_engine
from 组合回测.统一多股执行器 import 运行共享账户回测


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "1_策略配置")
DATA = os.path.join(ROOT, "数据模块", "raw", "600519_双价格合并.pkl")


def test_shared_account_view_is_stock_scoped_but_risk_is_portfolio_wide():
    account = 交易账户(100_000)
    a = account.股票视图("600001")
    b = account.股票视图("600002")
    a.持仓["SH_600001"] = {"股数": 100, "买入价": 100.0}
    a.更新估值价(100.0)

    assert list(a.持仓) == ["SH_600001"]
    assert list(b.持仓) == []
    assert b.已达到最大持仓数(1) is True
    assert b.已达到最大持仓数(0) is False

    available, limits = b.计算结构性可用金额(
        estimate_price=50.0,
        max_single_ratio=0.30,
        max_total_ratio=0.50,
        cash_floor=0.20,
    )
    assert limits["当前权益"] == pytest.approx(110_000)
    assert limits["持仓市值"] == pytest.approx(10_000)
    assert available == pytest.approx(33_000)


def test_zero_total_position_ratio_disables_only_total_position_cap():
    account = 交易账户(100_000)
    view = account.股票视图("600001")
    view.持仓["SH_600001"] = {"股数": 100, "买入价": 100.0}
    view.更新估值价(100.0)

    available, limits = view.计算结构性可用金额(
        estimate_price=50.0,
        max_single_ratio=0.30,
        max_total_ratio=0.0,
        cash_floor=0.20,
    )

    assert available == pytest.approx(31_500)
    assert limits["总仓位限制已关闭"] is True


def test_zero_single_and_total_position_ratios_leave_cash_as_only_limit():
    account = 交易账户(100_000)
    view = account.股票视图("600001")

    available, limits = view.计算结构性可用金额(
        estimate_price=50.0,
        max_single_ratio=0.0,
        max_total_ratio=0.0,
        cash_floor=0.0,
    )

    assert available == pytest.approx(100_000)
    assert limits["单只仓位限制已关闭"] is True
    assert limits["总仓位限制已关闭"] is True


@pytest.mark.skipif(not os.path.isfile(DATA), reason="缺少600519本地行情")
def test_shared_account_partially_fills_without_repricing_or_negative_cash(tmp_path):
    config = tmp_path / "config"
    shutil.copytree(CONFIG, config)
    positions_path = config / "仓位配置.yaml"
    positions = yaml.safe_load(positions_path.read_text(encoding="utf-8"))
    positions["基准仓位"]["基础单只金额"] = 500_000
    positions_path.write_text(
        yaml.safe_dump(positions, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    buys_path = config / "买入信号配置.yaml"
    buys = yaml.safe_load(buys_path.read_text(encoding="utf-8"))
    for item in buys["买入信号列表"]:
        item["单笔买入上限"] = 500_000
    buys_path.write_text(
        yaml.safe_dump(buys, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    run = 运行共享账户回测(
        ["600519"], "2020-01-01", "2023-12-31", 2_000_000,
        str(config), liquidity_limit=0.01, allow_partial_fill=True,
    )
    account = run["账户"]
    partial = [
        row for row in account.审批记录
        if row.get("审批状态") == "部分成交"
    ]

    assert partial
    assert account.现金 >= 0
    assert all(row["成交股数"] < row["请求股数"] for row in partial)
    assert all(row["成交价"] > 0 for row in partial)
    assert all("网格层级" in row for row in partial)


@pytest.mark.skipif(not os.path.isfile(DATA), reason="缺少600519本地行情")
def test_two_stock_engines_share_one_position_limit_and_real_cash(tmp_path, monkeypatch):
    config = tmp_path / "config"
    shutil.copytree(CONFIG, config)
    positions_path = config / "仓位配置.yaml"
    positions = yaml.safe_load(positions_path.read_text(encoding="utf-8"))
    positions["基准仓位"]["最大总持仓数"] = 1
    positions_path.write_text(
        yaml.safe_dump(positions, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    base, _, params, technical = 准备回测数据(
        "600519", "2020-01-01", "2023-12-31", str(config)
    )

    def cloned_data(stock, start, end, config_dir):
        data = base.copy()
        data["股票代码"] = f"SH_{stock}"
        return data, config_dir, params, technical

    monkeypatch.setattr(multi_engine, "准备回测数据", cloned_data)
    run = 运行共享账户回测(
        ["600519", "600520"], "2020-01-01", "2023-12-31", 2_000_000,
        str(config), liquidity_limit=0.01,
    )
    account = run["账户"]

    assert len(account.持仓) <= 1
    assert account.现金 >= 0
    assert any(row.get("原因") == "达到最大持仓数量" for row in account.审批记录)
    assert run["live"]["拒绝原因汇总"]["达到最大持仓数量"] > 0
    assert {result["股票代码"] for result in run["股票结果"]} == {"600519", "600520"}
