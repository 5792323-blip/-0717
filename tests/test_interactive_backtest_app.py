import os
import shutil
import re
import json
from unittest.mock import patch

import yaml

from 运行程序.interactive_backtest_app import (
    应用表单到配置, 应用, 构建默认表单, 构建工作台表单,
    保存最近工作台配置, 获取当前单票回放地址, 获取多股票回放地址,
    运行交互回测, 启动后台回测, 回测进度, 提取模式配置, 规范化表单, 预检查无成交风险,
    _保存回测检查点, 回测检查点, 提取组合基准指标, 修复旧版回放脚本,
    格式化可选百分比,
)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "1_策略配置")


def test_extracts_hs300_and_excess_return_from_portfolio_curve():
    metrics = 提取组合基准指标(
        [{"沪深300权益": 1000000}, {"沪深300权益": 1220000}],
        1000000,
        35.0,
    )

    assert metrics == {"沪深300收益率": 22.0, "超额收益率": 13.0}


def test_shared_attribution_mode_marks_undefined_win_rate_unavailable():
    """共享账户股票归因不提供账户级胜率时，页面完成摘要不能转换 None。"""
    assert 格式化可选百分比(None) == "--"
    assert 格式化可选百分比(0.625) == "62.50%"


def test_normalize_form_preserves_boolean_module_switches():
    form = 构建默认表单()
    form["single_switch_买入规则_rsi_cross_20"] = True
    form["multi_switch_买入规则_rsi_cross_20"] = True

    normalized = 规范化表单(form)

    assert normalized["single_switch_买入规则_rsi_cross_20"] is True
    assert normalized["multi_switch_买入规则_rsi_cross_20"] is True


def test_workbench_template_separates_single_and_multi_sections():
    source = open(os.path.join(ROOT, "运行程序", "interactive_backtest_app.py"), encoding="utf-8").read()

    assert "document.querySelectorAll('[data-mode-section]')" in source
    assert "node.hidden = node.dataset.modeSection !== mode;" in source


def test_workbench_template_keeps_module_parameter_inputs_full_width():
    source = open(os.path.join(ROOT, "运行程序", "interactive_backtest_app.py"), encoding="utf-8").read()

    assert ".param-row {\n      display: grid;\n      grid-template-columns: minmax(0, 1fr);" in source
    assert ".param-row input,\n    .param-row textarea {\n      width: 100%;" in source


def test_normalize_form_accepts_serialized_historical_constituents_flag():
    form = 构建默认表单()
    form["multi_historical_constituents"] = "True"

    normalized = 规范化表单(form)

    assert normalized["multi_historical_constituents"] is True


def test_repairs_legacy_rsi_attribution_script_without_changing_other_html():
    legacy = "<script>group.buys.reduce((sum,buy)=>sum+(Number(buy['总成本'])||((Number(buy['买入价'])||0)*(Number(buy['成交数量'])||0)),0);</script>"

    repaired = 修复旧版回放脚本(legacy)

    assert repaired == "<script>group.buys.reduce((sum,buy)=>sum+(Number(buy['总成本'])||((Number(buy['买入价'])||0)*(Number(buy['成交数量'])||0))),0);</script>"


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
        "single_entry_timing": "same_bar_entry",
        "single_sell_timing": "next_bar_open",
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
    assert parameters["卖出参数"]["卖出时机模式"] == "next_bar_open"
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


def test_grid_initial_ratio_applies_to_non_full_position_first_request(tmp_path):
    snapshot = tmp_path / "config"
    shutil.copytree(CONFIG, snapshot)
    form = 构建默认表单()
    form.update({
        "single_full_position_mode": False,
        "single_capital": 10000000,
        "single_base_position": 10000000,
        "single_grid_initial_ratio": 0.1,
        "single_switch_扩展因子_grid_addon": True,
    })

    应用表单到配置(snapshot, 提取模式配置(form, "single"))

    positions = yaml.safe_load((snapshot / "仓位配置.yaml").read_text(encoding="utf-8"))
    parameters = yaml.safe_load((snapshot / "参数配置.yaml").read_text(encoding="utf-8"))
    assert positions["基准仓位"]["基础单只金额"] == 1000000
    assert parameters["仓位参数"]["基础单只金额"] == 1000000


def test_lifecycle_budget_grid_forces_first_ratio_and_persists_budget(tmp_path):
    snapshot = tmp_path / "config"
    shutil.copytree(CONFIG, snapshot)
    form = 构建默认表单()
    form.update({
        "ui_mode": "single",
        "single_full_position_mode": False,
        "single_capital": 10000000,
        "single_base_position": 1000000,
        "single_grid_mode": "lifecycle_budget",
        "single_grid_initial_ratio": 0.8,
        "single_switch_扩展因子_grid_addon": True,
    })

    normalized = 规范化表单(form)
    assert normalized["single_grid_initial_ratio"] == 0.25
    应用表单到配置(snapshot, 提取模式配置(normalized, "single"))

    positions = yaml.safe_load((snapshot / "仓位配置.yaml").read_text(encoding="utf-8"))
    factors = yaml.safe_load((snapshot / "因子配置.yaml").read_text(encoding="utf-8"))
    grid = factors["因子列表"]["grid_addon"]["参数"]
    assert positions["基准仓位"]["基础单只金额"] == 250000
    assert grid["加仓模式"] == "lifecycle_budget"
    assert grid["最大加仓次数"] == 4
    assert grid["生命周期预算金额"] == 1000000
    assert grid["生命周期预算比例"] == [0.25, 0.15, 0.2, 0.2, 0.2]


def test_next_bar_entry_does_not_enable_same_bar_entry_when_saved(tmp_path):
    snapshot = tmp_path / "config"
    shutil.copytree(CONFIG, snapshot)
    form = 构建默认表单()
    form.update({
        "single_entry_timing": "precomputed_stop_entry",
        "single_switch_核心模块_same_bar_entry": False,
        "single_switch_核心模块_next_bar_entry": True,
    })

    应用表单到配置(snapshot, 提取模式配置(form, "single"))

    parameters = yaml.safe_load((snapshot / "参数配置.yaml").read_text(encoding="utf-8"))
    switches = yaml.safe_load((snapshot / "模块开关配置.yaml").read_text(encoding="utf-8"))
    core = yaml.safe_load((snapshot / "核心模块配置.yaml").read_text(encoding="utf-8"))
    assert parameters["买入参数"]["买入时机模式"] == "precomputed_stop_entry"
    assert parameters["技术指标参数"]["哨兵价本根形成立即买入"] is False
    assert switches["模块类别"]["核心模块"]["same_bar_entry"]["启用"] is False
    assert switches["模块类别"]["核心模块"]["next_bar_entry"]["启用"] is True
    assert core["核心模块"]["本根形成立即成交"]["启用"] is False
    assert core["核心模块"]["下一根执行"]["启用"] is True


def test_save_config_persists_execution_timing_to_formal_config(tmp_path):
    config_dir = tmp_path / "config"
    shutil.copytree(CONFIG, config_dir)
    workbench_path = tmp_path / "workbench.json"
    with patch("运行程序.interactive_backtest_app.正式配置目录", str(config_dir)), \
         patch("运行程序.interactive_backtest_app.工作台配置路径", str(workbench_path)), \
         patch("运行程序.interactive_backtest_app.实验记录目录", str(tmp_path / "records")):
        form = 构建默认表单()
        form.update({
            "single_entry_timing": "precomputed_stop_entry",
            "single_switch_核心模块_same_bar_entry": False,
            "single_switch_核心模块_next_bar_entry": True,
        })
        data = {key: value for key, value in form.items()}
        data.update({
            "ui_mode": "single",
            "save_config": "1",
            "single_entry_timing": "precomputed_stop_entry",
            "single_switch_核心模块_same_bar_entry": "",
            "single_switch_核心模块_next_bar_entry": "on",
        })
        response = 应用.test_client().post("/", data=data)

    assert response.status_code == 200
    parameters = yaml.safe_load((config_dir / "参数配置.yaml").read_text(encoding="utf-8"))
    switches = yaml.safe_load((config_dir / "模块开关配置.yaml").read_text(encoding="utf-8"))
    assert parameters["买入参数"]["买入时机模式"] == "precomputed_stop_entry"
    assert parameters["技术指标参数"]["哨兵价本根形成立即买入"] is False
    assert switches["模块类别"]["核心模块"]["same_bar_entry"]["启用"] is False
    assert switches["模块类别"]["核心模块"]["next_bar_entry"]["启用"] is True


def test_legacy_core_switch_can_select_timing_when_dropdown_is_absent():
    form = 规范化表单({
        "ui_mode": "single",
        "single_switch_核心模块_same_bar_entry": "on",
        "single_switch_核心模块_next_bar_entry": "",
    })
    assert form["single_entry_timing"] == "same_bar_entry"
    assert form["single_switch_核心模块_same_bar_entry"] is True
    assert form["single_switch_核心模块_next_bar_entry"] is False


def test_explicit_strict_timing_wins_over_stale_same_bar_core_switch():
    """新版页面的时序下拉是权威输入，不能被旧复选框反向覆盖。"""
    form = 规范化表单({
        "ui_mode": "multi",
        "multi_entry_timing": "precomputed_stop_entry",
        "multi_switch_核心模块_same_bar_entry": "on",
        "multi_switch_核心模块_next_bar_entry": "",
    })
    assert form["multi_entry_timing"] == "precomputed_stop_entry"
    assert form["multi_switch_核心模块_same_bar_entry"] is False
    assert form["multi_switch_核心模块_next_bar_entry"] is True


def test_multi_timing_dropdown_syncs_the_core_switches_in_browser_script():
    source = open(os.path.join(ROOT, "运行程序", "interactive_backtest_app.py"), encoding="utf-8").read()

    assert "if (node.name === 'multi_entry_timing') setEntryTiming('multi', node.value);" in source


def test_home_page_renders():
    client = 应用.test_client()
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "回测主页面" in body
    assert "单股账户" in body
    assert "多股账户" in body
    assert "运行单股回测" in body
    assert "运行多股回测" in body
    assert "公共策略配置" in body
    assert "策略与账户设置" in body
    assert "严格预挂单下，1.001 代表成交价上限上浮 0.1%" in body
    assert "updateEffectiveConfig" in body
    assert 'id="backtestProgress"' in body
    assert "pollProgress" in body
    assert "有效订单金额预览" in body
    assert "首次开仓时机" in body
    assert "网格加仓时机" in body
    assert "资金基准金额" in body
    assert "各信号资金计划" in body
    assert "线性加仓：L0=1 / L1=2 / L2=3 / L3=4 / L4=5" in body
    assert "倍数加仓：L0=1 / L1=2 / L2=4 / L3=8 / L4=16" in body
    assert "单只股票累计仓位上限比例" in body
    assert "组合总持仓上限比例" in body
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
    # 首页在没有历史回测快照时不会生成 /report/<token>。这里只验证
    # 报告容器存在，避免测试结果依赖开发机上是否残留旧报告。
    assert 'id="viewer-report"' in body
    assert "分批止盈第三档" in body
    assert "下一根K线执行" in body
    assert 'name="single_switch_扩展因子_xgboost_trend"' in body
    assert 'name="single_switch_扩展因子_xgboost_trend"' in body and "disabled" in body
    assert re.search(r"① 入场信号</span><span class=\"fold-count\">4 项（\d+项）</span>", body)
    assert re.search(r"② 入场确认与过滤</span><span class=\"fold-count\">25 项（\d+项）</span>", body)
    assert "③ 仓位与网格" in body
    assert "④ 成交执行" in body
    assert "⑤ 卖出与持仓管理" in body
    assert "⑥ 实验与研究" in body
    assert 'id="selectedStrategy"' in body
    assert "updateSelectedStrategy" in body
    assert "最大持仓股数" in body
    assert "拒绝订单汇总" in body


def test_backtest_progress_endpoint_returns_idle_state():
    response = 应用.test_client().get("/api/backtest-progress")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] in {"idle", "running", "completed", "failed"}
    assert {"completed", "total", "trades", "phase"}.issubset(payload)


def test_live_metrics_endpoint_returns_read_only_snapshot():
    response = 应用.test_client().get("/api/backtest-live")
    assert response.status_code == 200
    payload = response.get_json()
    assert {"status", "phase", "live"}.issubset(payload)


def test_stop_endpoint_rejects_when_no_backtest_is_running():
    response = 应用.test_client().post("/api/backtest-stop")
    assert response.status_code == 409


def test_checkpoint_is_readable_and_keeps_recent_curve(tmp_path):
    task_id = "checkpoint-test"
    run_dir = str(tmp_path / "run")
    _保存回测检查点(
        task_id, run_dir, completed=2, total=10, phase="共享账户时间轴回测",
        live={"当前权益": 101000}, curve_point={"日期": "2020-01-02", "权益": 101000},
    )
    payload = json.loads((tmp_path / "run" / "checkpoint" / "latest.json").read_text(encoding="utf-8"))
    assert payload["completed"] == 2
    assert payload["live"]["当前权益"] == 101000
    assert payload["曲线"][-1]["权益"] == 101000


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


def test_modes_share_strategy_but_keep_account_configuration_isolated():
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


def test_multi_submission_uses_its_explicit_public_strategy_values():
    form = 构建默认表单()
    form["single_entry_timing"] = "same_bar_entry"
    form["single_switch_核心模块_same_bar_entry"] = True
    form["single_switch_核心模块_next_bar_entry"] = False
    form["multi_entry_timing"] = "precomputed_stop_entry"
    form["multi_switch_核心模块_same_bar_entry"] = False
    form["multi_switch_核心模块_next_bar_entry"] = True

    multi = 提取模式配置(form, "multi")

    assert multi["entry_timing"] == "precomputed_stop_entry"
    assert multi["switch_核心模块_same_bar_entry"] is False
    assert multi["switch_核心模块_next_bar_entry"] is True


def test_normalized_form_mirrors_public_strategy_without_copying_accounts():
    normalized = 规范化表单({
        "ui_mode": "single",
        "single_capital": "12000000",
        "multi_capital": "8000000",
        "single_rsi_period": "9",
        "single_grid_mode": "linear",
        "single_switch_买入规则_rsi_cross_20": "on",
        "single_param_买入规则_rsi_cross_20_单笔买入上限": "750000",
    })

    assert normalized["single_capital"] == 12000000
    assert normalized["multi_capital"] == 8000000
    assert normalized["single_rsi_period"] == normalized["multi_rsi_period"] == 9
    assert normalized["single_grid_mode"] == normalized["multi_grid_mode"] == "linear"
    assert normalized["single_switch_买入规则_rsi_cross_20"] is True
    assert normalized["multi_switch_买入规则_rsi_cross_20"] is True
    assert normalized["multi_param_买入规则_rsi_cross_20_单笔买入上限"] == 750000


def test_single_full_position_mode_passes_runtime_flag(tmp_path):
    form = 构建默认表单()
    form["single_full_position_mode"] = True
    form["single_stock"] = "600519"

    with patch("运行程序.interactive_backtest_app.创建运行目录", return_value=str(tmp_path)), \
         patch("运行程序.interactive_backtest_app.复制配置", return_value=str(tmp_path)), \
         patch("运行程序.interactive_backtest_app.清理旧交互回测数据"), \
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


def test_single_backtest_publishes_run_directory_before_execution(tmp_path):
    form = 构建默认表单()
    progress = []
    with patch("运行程序.interactive_backtest_app.创建运行目录", return_value=str(tmp_path)), \
         patch("运行程序.interactive_backtest_app.复制配置", return_value=str(tmp_path)), \
         patch("运行程序.interactive_backtest_app.清理旧交互回测数据"), \
         patch("运行程序.interactive_backtest_app.应用表单到配置"), \
         patch("运行程序.interactive_backtest_app.跑回测", return_value={
             "总收益率": 0.0, "最大回撤": 0.0, "胜率": 0.0,
             "最终权益": 10000000, "买入次数": 0, "卖出次数": 0,
             "原始K线数据": None,
         }), \
         patch("运行程序.interactive_backtest_app.保存结果"), \
         patch("运行程序.interactive_backtest_app.生成报告"):
        运行交互回测(form, progress=lambda **changes: progress.append(changes))

    assert any(item.get("run_dir") == str(tmp_path) for item in progress)


def test_new_backtest_cleans_previous_interactive_outputs():
    form = 构建默认表单()
    回测进度.clear()
    with patch("运行程序.interactive_backtest_app.清理旧交互回测数据") as cleanup, \
         patch("运行程序.interactive_backtest_app.threading.Thread") as thread:
        task_id = 启动后台回测(form, "multi")

    cleanup.assert_called_once_with()
    thread.return_value.start.assert_called_once_with()
    assert task_id
    回测进度.clear()


def test_precheck_blocks_zero_trade_risk():
    form = 构建默认表单()
    form["single_full_position_mode"] = False
    form["single_max_single_ratio"] = 0.0001
    issues = 预检查无成交风险(form, "single")
    assert any("单只股票累计仓位上限比例过低" in item for item in issues)


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
    assert restored["multi_switch_扩展因子_grid_addon"] is True
    assert restored["multi_switch_过滤因子_index_trend_filter"] is False


def test_unchecked_strategy_switch_is_saved_as_disabled():
    form = 规范化表单({"save_config": "1"})
    assert form["single_switch_卖出规则_atr_trailing"] is False
    assert form["multi_switch_卖出规则_atr_trailing"] is False
