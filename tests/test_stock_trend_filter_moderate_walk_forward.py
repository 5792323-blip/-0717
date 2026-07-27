from 研究实验.stock_trend_filter_moderate_walk_forward import 活跃度告警, 中等阈值


def test_activity_guard_rejects_zero_trade_candidate():
    assert 活跃度告警({"总交易数": 0}, 300)["通过"] is False
    assert 中等阈值["长均线下偏离上限"] == 0.08
