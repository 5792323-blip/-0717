import json

from 基本面.联合评分管线 import 运行


def test_pipeline_reports_missing_real_snapshot(tmp_path, monkeypatch):
    import 基本面.联合评分管线 as pipeline

    monkeypatch.setattr(pipeline, "SNAPSHOT", tmp_path / "missing.csv")
    monkeypatch.setattr(pipeline, "REPORT", tmp_path / "report.json")
    result = 运行()
    assert not result["通过"]
    assert result["联合模块可启用"] is False
    assert (tmp_path / "report.json").exists()
