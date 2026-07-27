from 研究实验.grid_risk_sensitivity_experiment import 解析方案


def test_parse_grid_risk_plans():
    assert 解析方案("宽松:3:60,严格:10:20") == [
        ("宽松", 3, 60),
        ("严格", 10, 20),
    ]
