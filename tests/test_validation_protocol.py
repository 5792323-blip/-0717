from 研究实验.validation_protocol import (
    评估失效,
    评估Walk_forward,
    生成消融方案,
    生成_walk_forward区间,
)


def test_ablation_plan_contains_baseline_and_one_factor_changes():
    plans = 生成消融方案([("过滤因子", "factor_a")])
    assert plans[0]["名称"] == "基线"
    assert len(plans) == 3
    assert plans[1]["开启"] == [{"类别": "过滤因子", "模块": "factor_a"}]


def test_walk_forward_windows_keep_validation_after_training():
    windows = 生成_walk_forward区间("2020-01-01", "2024-12-31", train_years=2)
    assert windows[0]["训练期"] == ["2020-01-01", "2021-12-31"]
    assert windows[0]["验证期"] == ["2022-01-01", "2022-12-31"]
    assert len(windows) == 3


def test_failure_protocol_prioritizes_drawdown_and_ratio():
    result = 评估失效({
        "平均年化收益率": 0.05, "平均最大回撤": 0.30,
        "加权胜率": 0.5, "平均盈亏比": 0.8, "总交易数": 100,
    })
    assert result["通过"] is False
    assert {item["指标"] for item in result["告警"]} >= {"最大回撤", "盈亏比"}


def test_walk_forward_requires_all_windows_to_pass():
    good = {"平均年化收益率": .05, "平均最大回撤": .10, "加权胜率": .5,
            "平均盈亏比": 1.2, "总交易数": 100}
    bad = {**good, "平均最大回撤": .30}
    result = 评估Walk_forward({"2022": good, "2023": {"基线": good, "候选": bad}})
    assert result["通过"] is False
    assert result["窗口结果"][1]["通过"] is False
