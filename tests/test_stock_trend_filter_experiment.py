from 研究实验.stock_trend_filter_experiment import 设置趋势准入


def test_trend_filter_switches_legacy_and_central_configs(tmp_path):
    (tmp_path / "过滤因子配置.yaml").write_text(
        "过滤因子列表:\n  - 英文标识: stock_trend_universe_filter\n    启用: false\n", encoding="utf-8"
    )
    (tmp_path / "模块开关配置.yaml").write_text(
        "模块类别:\n  过滤因子:\n    stock_trend_universe_filter:\n      启用: false\n", encoding="utf-8"
    )
    设置趋势准入(str(tmp_path), True)
    assert "启用: true" in (tmp_path / "过滤因子配置.yaml").read_text(encoding="utf-8")
    assert "启用: true" in (tmp_path / "模块开关配置.yaml").read_text(encoding="utf-8")
