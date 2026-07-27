from 研究实验.rsi70_resonance_walk_forward_experiment import 设置共振


def test_resonance_enables_legacy_and_central_switches(tmp_path):
    (tmp_path / "过滤因子配置.yaml").write_text(
        "过滤因子列表:\n  - 英文标识: rsi_resonance_filter\n    启用: false\n", encoding="utf-8"
    )
    (tmp_path / "模块开关配置.yaml").write_text(
        "模块类别:\n  过滤因子:\n    rsi_resonance_filter:\n      启用: false\n", encoding="utf-8"
    )
    设置共振(str(tmp_path), 1)
    assert "启用: true" in (tmp_path / "过滤因子配置.yaml").read_text(encoding="utf-8")
    assert "启用: true" in (tmp_path / "模块开关配置.yaml").read_text(encoding="utf-8")
