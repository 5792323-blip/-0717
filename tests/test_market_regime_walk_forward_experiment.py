from 研究实验.market_regime_walk_forward_experiment import 设置市场状态


def test_market_regime_switches_both_configs(tmp_path):
    (tmp_path / "过滤因子配置.yaml").write_text(
        "过滤因子列表:\n  - 英文标识: market_regime_filter\n    启用: false\n", encoding="utf-8"
    )
    (tmp_path / "模块开关配置.yaml").write_text(
        "模块类别:\n  过滤因子:\n    market_regime_filter:\n      启用: false\n", encoding="utf-8"
    )
    设置市场状态(str(tmp_path), True)
    assert "启用: true" in (tmp_path / "过滤因子配置.yaml").read_text(encoding="utf-8")
    assert "启用: true" in (tmp_path / "模块开关配置.yaml").read_text(encoding="utf-8")
