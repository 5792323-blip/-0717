import os
import shutil

import pytest
import yaml

from 研究实验.module_ablation_backtest import 复制并设置模块, 计算差异, 设置最大持仓数
from 模块系统 import 模块开关管理器, 模块配置错误
from 模块系统.模块运行器 import 审计全部, 独立运行
from 策略引擎.规则执行器 import 规则执行器


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "1_策略配置")


def test_formal_switches_preserve_current_strategy():
    manager = 模块开关管理器(CONFIG)
    assert manager.是否启用("买入规则", "rsi_cross_20") is True
    assert manager.是否启用("过滤因子", "rsi_ma_filter") is True
    assert manager.是否启用("卖出规则", "atr_trailing") is True
    assert manager.是否启用("卖出规则", "rsi_guard") is False
    assert manager.统计()["已启用"] == 10


def test_unready_module_cannot_be_enabled(tmp_path):
    target = tmp_path / "config"
    shutil.copytree(CONFIG, target)
    path = target / "模块开关配置.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["模块类别"]["扩展因子"]["xgboost_trend"]["启用"] = True
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    with pytest.raises(模块配置错误, match="未就绪"):
        模块开关管理器(target)


def test_executor_uses_central_switches():
    executor = 规则执行器(CONFIG)
    assert {item["名称"] for item in executor.买入规则列表} == {
        "rsi_cross_20", "rsi_cross_30", "rsi_cross_ma", "rsi_cross_70"
    }
    assert {item["名称"] for item in executor.卖出规则列表} == {"atr_trailing"}
    assert {item["名称"] for item in executor.过滤因子列表} == {"rsi_ma_filter"}
    assert executor.哨兵价本根形成立即买入 is False


def test_ablation_copy_changes_only_requested_switch(tmp_path):
    target = tmp_path / "candidate"
    复制并设置模块(CONFIG, target, "过滤因子", "rsi_ma_filter", False)
    source_manager = 模块开关管理器(CONFIG)
    target_manager = 模块开关管理器(target)
    changed = [
        (a["类别"], a["标识"])
        for a, b in zip(source_manager.扁平清单(), target_manager.扁平清单())
        if a["启用"] != b["启用"]
    ]
    assert changed == [("过滤因子", "rsi_ma_filter")]


def test_all_modules_import_and_ready_module_runs_independently():
    manager = 模块开关管理器(CONFIG)
    audit = 审计全部(manager)
    assert audit["审计通过"] is True
    item = manager.获取("买入规则", "rsi_cross_20")
    result = 独立运行("买入规则", item, {"上一根RSI": 18, "当前RSI": 21})
    assert result["触发"] is True


def test_ablation_delta_is_opened_minus_closed():
    assert 计算差异({"收益": 0.1, "标签": "关"}, {"收益": 0.13, "标签": "开"}) == {
        "收益": pytest.approx(0.03)
    }


def test_ablation_snapshot_can_set_max_positions(tmp_path):
    target = tmp_path / "positions"
    shutil.copytree(CONFIG, target)
    设置最大持仓数(target, 300)
    positions = yaml.safe_load((target / "仓位配置.yaml").read_text(encoding="utf-8"))
    parameters = yaml.safe_load((target / "参数配置.yaml").read_text(encoding="utf-8"))
    assert positions["基准仓位"]["最大总持仓数"] == 300
    assert parameters["仓位参数"]["最大持仓数"] == 300
