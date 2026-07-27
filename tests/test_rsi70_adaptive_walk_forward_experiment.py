from 研究实验.rsi70_adaptive_walk_forward_experiment import 设置自适应


def test_adaptive_enables_legacy_and_central_switches(tmp_path):
    (tmp_path / "过滤因子配置.yaml").write_text(
        "过滤因子列表:\n  - 英文标识: rsi_regime_adaptive_filter\n    启用: false\n", encoding="utf-8"
    )
    (tmp_path / "模块开关配置.yaml").write_text(
        "模块类别:\n  过滤因子:\n    rsi_regime_adaptive_filter:\n      启用: false\n", encoding="utf-8"
    )
    设置自适应(str(tmp_path))
    assert "启用: true" in (tmp_path / "过滤因子配置.yaml").read_text(encoding="utf-8")
    assert "启用: true" in (tmp_path / "模块开关配置.yaml").read_text(encoding="utf-8")
