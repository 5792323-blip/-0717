from 研究实验.stock_trend_filter_walk_forward_experiment import 严格阈值


def test_strict_thresholds_are_conservative():
    assert 严格阈值["长均线下偏离上限"] == 0.05
    assert 严格阈值["中期高点回撤上限"] == 0.20
