import yaml

from 研究实验.grid_risk_limits_experiment import 设置网格风控


def test_grid_risk_experiment_changes_only_candidate_parameters(tmp_path):
    config = tmp_path / "因子配置.yaml"
    config.write_text("因子列表:\n  grid_addon:\n    参数:\n      启用风控限制: false\n", encoding="utf-8")
    设置网格风控(str(tmp_path), True, 5, 30)
    value = yaml.safe_load(config.read_text(encoding="utf-8"))
    params = value["因子列表"]["grid_addon"]["参数"]
    assert params["启用风控限制"] is True
    assert params["最小加仓间隔K线"] == 5
    assert params["禁止加仓持仓K线数"] == 30
