from 研究实验.stock_trend_filter_sensitivity_experiment import 方案


def test_sensitivity_has_ordered_threshold_profiles():
    assert set(方案) == {"宽松", "当前", "严格"}
    assert 方案["宽松"]["长均线下偏离上限"] > 方案["严格"]["长均线下偏离上限"]
