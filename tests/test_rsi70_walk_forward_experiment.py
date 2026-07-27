from 研究实验.rsi70_walk_forward_experiment import 设置关闭_rsi70


def test_rsi70_disables_both_legacy_and_central_switches(tmp_path):
    (tmp_path / "买入信号配置.yaml").write_text(
        "买入信号列表:\n  - 英文标识: rsi_cross_70\n    启用: true\n", encoding="utf-8"
    )
    (tmp_path / "模块开关配置.yaml").write_text(
        "模块类别:\n  买入规则:\n    rsi_cross_70:\n      启用: true\n", encoding="utf-8"
    )
    设置关闭_rsi70(str(tmp_path))
    assert "启用: false" in (tmp_path / "买入信号配置.yaml").read_text(encoding="utf-8")
    assert "启用: false" in (tmp_path / "模块开关配置.yaml").read_text(encoding="utf-8")
