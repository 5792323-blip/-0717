from 研究实验.grid_risk_walk_forward_experiment import 运行方案


def test_walk_forward_module_exposes_candidate_runner():
    assert callable(运行方案)
