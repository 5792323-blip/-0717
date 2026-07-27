from 研究实验.rsi_adaptive_sensitivity_experiment import 解析方案


def test_parse_adaptive_period_plans():
    assert 解析方案("10:40,20:60") == [(10, 40), (20, 60)]
