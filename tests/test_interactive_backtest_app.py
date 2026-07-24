import os
import shutil
import re
from unittest.mock import patch

import yaml

from 运行程序.interactive_backtest_app import (
    应用表单到配置, 应用, 构建默认表单, 构建工作台表单,
    保存最近工作台配置, 获取当前单票回放地址, 获取多股票回放地址,
    运行交互回测, 提取模式配置, 预检查无成交风险,
)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "1_策略配置")


def test_apply_form_updates_snapshot(tmp_path):
    snapshot = tmp_path / "config"
    shutil.copytree(CONFIG, snapshot)
    form = 构建默认表单()
    form.update({
        "single_capital": 50000000,
        "single_base_position": 500000,
        "single_max_positions": 300,
        "single_max_single_ratio": 0.12,
        "single_max_total_ratio": 0.9,
        "single_cash_floor": 0.1,
        "single_rsi_period": 10,
        "single_rsi_ma_period": 15,
        "single_atr_period": 12,
        "single_buy_premium": 1.002,
        "single_slippage": 0.002,
        "single_commission": 0.0003,
        "single_stamp_tax": 0.0015,
        "single_transfer_fee": 0.00002,
        "single_signal_expiry_bars": 48,
        "single_atr_exit_multiple": 3.2,
        "single_hard_stop_multiple": 4.0,
        "single_take_profit_1": 0.06,
        "single_take_profit_2": 0.12,
        "single_take_profit_3": 0.24,
        "single_guard_atr_buffer": 0.8,
        "single_momentum_decline": 18,
        "single_time_exit_bars": 50,
        "single_time_exit_loss": -0.05,
        "single_switch_卖出规则_rsi_guard": True,
        "single_switch_卖出规则_time_exit": True,
        "single_switch_过滤因子_rsi_ma_filter": False,
        "single_switch_过滤因子_index_trend_filter": True,
        "single_switch_扩展因子_market_state": True,
        "single_switch_核心模块_same_bar_entry": True,
        "single_switch_核心模块_next_bar_entry": False,
        "single_param_卖出规则_take_profit_第一目标": 0.06,
        "single_param_卖出规则_take_profit_第二目标": 0.12,
        "single_param_卖出规则_take_profit_第三目标": 0.24,
        "single_param_卖出规则_stop_loss_止损倍数": 4.0,
        "single_param_卖出规则_rsi_guard_ATR缓冲倍数": 0.8,
        "single_param_卖出规则_momentum_exit_基础回落阈值": 18,
        "single_param_卖出规则_time_exit_最大持仓K线数": 50,
        "single_param_卖出规则_time_exit_亏损触发": -0.05,
        "single_param_卖出规则_atr_trailing_ATR倍数": 3.2,
    })

    应用表单到配置(snapshot, 提取模式配置(form, "single"))

    positions = yaml.safe_load((snapshot / "仓位配置.yaml").read_text(encoding="utf-8"))
    parameters = yaml.safe_load((snapshot / "参数配置.yaml").read_text(encoding="utf-8"))
    exits = yaml.safe_load((snapshot / "卖出规则配置.yaml").read_text(encoding="utf-8"))
    switches = yaml.safe_load((snapshot / "模块开关配置.yaml").read_text(encoding="utf-8"))
    filters = yaml.safe_load((snapshot / "过滤因子配置.yaml").read_text(encoding="utf-8"))
    factors = yaml.safe_load((snapshot / "因子配置.yaml").read_text(encoding="utf-8"))
    core = yaml.safe_load((snapshot / "核心模块配置.yaml").read_text(encoding="utf-8"))

    assert positions["基准仓位"]["初始资金"] == 50000000
    assert positions["基准仓位"]["最大总持仓数"] == 300
    assert parameters["技术指标参数"]["RSI周期"] == 10
    assert parameters["仓位参数"]["最大持仓数"] == 300
    assert parameters["交易成本"]["买入溢价"] == 1.002
    assert parameters["交易成本"]["印花税"] == 0.0015
    assert parameters["交易成本"]["过户费"] == 0.00002
    assert parameters["技术指标参数"]["信号过期K线数"] == 48
    assert parameters["卖出参数"]["分批止盈第三档"] == 0.24
    assert parameters["卖出参数"]["时间退出K线数"] == 50
    atr_rule = next(item for item in exits["卖出条件列表"] if item["英文标识"] == "atr_trailing")
    time_rule = next(item for item in exits["卖出条件列表"] if item["英文标识"] == "time_exit")
    assert atr_rule["ATR倍数"] == 3.2
    assert time_rule["最大持仓K线数"] == 50
    assert switches["模块类别"]["卖出规则"]["rsi_guard"]["启用"] is True
    assert switches["模块类别"]["卖出规则"]["time_exit"]["启用"] is True
    assert switches["模块类别"]["过滤因子"]["rsi_ma_filter"]["启用"] is False
    assert switches["模块类别"]["过滤因子"]["index_trend_filter"]["启用"] is True
    assert switches["模块类别"]["扩展因子"]["market_state"]["启用"] is True
    assert switches["模块类别"]["核心模块"]["same_bar_entry"]["启用"] is True
    assert next(x for x in filters["过滤因子列表"] if x["英文标识"] == "index_trend_filter")["启用"] is True
    assert factors["因子列表"]["market_state"]["启用"] is True
    assert core["核心模块"]["本根形成立即成交"]["启用"] is True
    assert core["核心模块"]["下一根执行"]["启用"] is False


def test_home_page_renders():
    client = 应用.test_client()
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "回测主页面" in body
    assert "单股模式" in body
    assert "多股模式" in body
    assert "运行单股回测" in body
    assert "运行多股回测" in body
    assert "基础回测参数" in body
    assert "资金、日期、仓位、指标" in body
    assert "RSI价格源" in body
    assert "收盘确认后次根开盘" in body
    assert "过滤因子" in body
    assert "扩展因子" in body
    assert "核心模块" in body
    assert "大盘状态" in body
    assert "RSI_MA因子" in body
    assert "XGBoost趋势" in body
    assert "RandomForest大盘" in body
    assert "ML假跌判断" in body
    assert "盈利8%平仓" in body
    assert "TB最低价RSI下穿卖出" in body
    assert "TB复刻模式（最高价RSI同根对照）" in body
    assert "应用TB复刻参数" in body
    assert "盈利阈值" in body
    assert "中性下限" in body
    assert "仅开关控制，无独立可调参数" in body
    assert "RSI阈值守仓（暂缓ATR）" in body
    assert "RSI中性区过滤" in body
    assert "RSI区间对齐过滤" in body
    assert "/report/" in body
    assert "/output/K线回放_600519.html" not in body
    assert "分批止盈第三档" in body
    assert "下一根K线执行" in body
    assert 'name="single_switch_扩展因子_xgboost_trend"' in body
    assert 'name="single_switch_扩展因子_xgboost_trend"' in body and "disabled" in body
    assert re.search(r"买入规则</span><span class=\"fold-count\">4 项（\d+项）</span>", body)
    assert re.search(r"卖出规则</span><span class=\"fold-count\">12 项（\d+项）</span>", body)
    assert re.search(r"过滤因子</span><span class=\"fold-count\">13 项（\d+项）</span>", body)
    assert re.search(r"扩展因子</span><span class=\"fold-count\">17 项（\d+项）</span>", body)
    assert re.search(r"核心模块</span><span class=\"fold-count\">6 项（\d+项）</span>", body)


def test_replay_uses_single_pan_zoom_workbench_template():
    template_path = os.path.join(ROOT, "回测引擎", "kline_template.html")
    template = open(template_path, encoding="utf-8").read()
    assert "策略决策回放台" in template
    assert "滚轮缩放" in template
    assert "拖动左右浏览" in template
    assert "allBarsMode" not in template
    assert "function showTip" in template


def test_output_urls_are_generated_from_stock_code():
    assert 获取当前单票回放地址("600519") == "/output/K线回放_600519.html"
    assert 获取多股票回放地址() == "/output/多股票K线回放.html"


def test_mode_config_isolated():
    form = 构建默认表单()
    form["single_capital"] = 111
    form["multi_capital"] = 222
    form["single_switch_核心模块_same_bar_entry"] = True
    form["multi_switch_核心模块_same_bar_entry"] = False
    single = 提取模式配置(form, "single")
    multi = 提取模式配置(form, "multi")
    assert single["capital"] == 111
    assert multi["capital"] == 222
    assert single["switch_核心模块_same_bar_entry"] is True
    assert multi["switch_核心模块_same_bar_entry"] is False


def test_single_full_position_mode_passes_runtime_flag(tmp_path):
    form = 构建默认表单()
    form["single_full_position_mode"] = True
    form["single_stock"] = "600519"

    with patch("运行程序.interactive_backtest_app.创建运行目录", return_value=str(tmp_path)), \
         patch("运行程序.interactive_backtest_app.复制配置", return_value=str(tmp_path)), \
         patch("运行程序.interactive_backtest_app.应用表单到配置") as apply_config, \
         patch("运行程序.interactive_backtest_app.跑回测") as run_backtest, \
         patch("运行程序.interactive_backtest_app.保存结果"), \
         patch("运行程序.interactive_backtest_app.生成报告"):
        run_backtest.return_value = {
            "总收益率": 0.0,
            "最大回撤": 0.0,
            "胜率": 0.0,
            "最终权益": 20000000,
            "买入次数": 1,
            "卖出次数": 1,
            "原始K线数据": None,
        }
        运行交互回测(form)

    apply_config.assert_called_once()
    assert run_backtest.call_args.kwargs["运行参数"]["单股全仓模式"] is True
    assert run_backtest.call_args.kwargs["运行参数"]["流动性上限比例"] == form["single_liquidity_limit"]


def test_precheck_blocks_zero_trade_risk():
    form = 构建默认表单()
    form["single_full_position_mode"] = False
    form["single_max_single_ratio"] = 0.0001
    issues = 预检查无成交风险(form, "single")
    assert any("最大单只比例过低" in item for item in issues)


def test_precheck_allows_default_single_setup():
    form = 构建默认表单()
    assert 预检查无成交风险(form, "single") == []


def test_workbench_configuration_survives_reload(tmp_path):
    form = 构建默认表单()
    form["single_switch_扩展因子_grid_addon"] = True
    form["multi_switch_过滤因子_index_trend_filter"] = True
    with patch("运行程序.interactive_backtest_app.工作台配置路径", str(tmp_path / "workbench.json")):
        保存最近工作台配置(form)
        restored = 构建工作台表单()
    assert restored["single_switch_扩展因子_grid_addon"] is True
    assert restored["multi_switch_过滤因子_index_trend_filter"] is True
