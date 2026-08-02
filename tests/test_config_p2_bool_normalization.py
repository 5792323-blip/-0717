"""CONFIG-P2-BOOL-NORMALIZATION red tests and controls."""

import pytest

from 运行程序.interactive_backtest_app import 规范化表单


PARAMETER = "single_param_过滤因子_index_trend_filter_历史不足时放行"


@pytest.mark.parametrize("raw_value", [True, "true", "True", "1"])
def test_module_boolean_parameter_accepts_true_representations(raw_value):
    normalized = 规范化表单({"ui_mode": "single", PARAMETER: raw_value})

    assert normalized[PARAMETER] is True


def test_module_boolean_parameter_accepts_checked_checkbox_value():
    normalized = 规范化表单({"ui_mode": "single", PARAMETER: "on"})

    assert normalized[PARAMETER] is True


@pytest.mark.parametrize("raw_value", [False, "false", "False", "0", "off", None])
def test_module_boolean_parameter_rejects_false_representations(raw_value):
    normalized = 规范化表单({"ui_mode": "single", PARAMETER: raw_value})

    assert normalized[PARAMETER] is False
