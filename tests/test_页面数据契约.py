import json

from 运行程序 import interactive_backtest_app as app_module


def test_多股报告路由读取运行目录中的页面(tmp_path):
    report = tmp_path / "多股策略决策回放.html"
    report.write_text("<html><body>运行目录页面</body></html>", encoding="utf-8")
    previous = dict(app_module.最近多股报告)
    app_module.最近多股报告.update({"token": "audit-token", "path": str(report), "run_dir": str(tmp_path)})
    try:
        response = app_module.应用.test_client().get("/multi-report/audit-token")
        assert response.status_code == 200
        assert "运行目录页面" in response.get_data(as_text=True)
    finally:
        app_module.最近多股报告.clear()
        app_module.最近多股报告.update(previous)


def test_运行生命周期接口读取同一运行清单(tmp_path):
    (tmp_path / "运行清单.json").write_text(
        json.dumps({"run_id": "audit-run", "locked": False}, ensure_ascii=False),
        encoding="utf-8",
    )
    previous = dict(app_module.回测进度)
    app_module.回测进度["run_dir"] = str(tmp_path)
    try:
        client = app_module.应用.test_client()
        response = client.get("/api/run-lifecycle")
        assert response.status_code == 200
        assert response.get_json()["run_id"] == "audit-run"
        response = client.post("/api/run-lifecycle", json={"action": "lock"})
        assert response.status_code == 200
        assert json.loads((tmp_path / "运行清单.json").read_text())["locked"] is True
    finally:
        app_module.回测进度.clear()
        app_module.回测进度.update(previous)


def test_深度行情删除后单票回放明确返回降级提示(tmp_path):
    stock_dir = tmp_path / "股票" / "600118"
    stock_dir.mkdir(parents=True)
    (tmp_path / "运行清单.json").write_text(json.dumps({"run_id": "degraded"}), encoding="utf-8")
    previous = dict(app_module.最近多股报告)
    app_module.最近多股报告.update({"token": "degraded-token", "path": None, "run_dir": str(tmp_path)})
    try:
        response = app_module.应用.test_client().get("/multi/degraded-token/stock/600118")
        assert response.status_code == 404
        assert "没有可用回放" in response.get_data(as_text=True)
    finally:
        app_module.最近多股报告.clear()
        app_module.最近多股报告.update(previous)


def test_服务重启后生命周期接口回退到最近完成运行(tmp_path, monkeypatch):
    run = tmp_path / "交互回测_完成_multi"
    run.mkdir()
    (run / "运行清单.json").write_text(json.dumps({"run_id": "recovered", "locked": True}), encoding="utf-8")
    (run / "多股回测结果.json").write_text(json.dumps({"股票明细": [], "汇总": {}}), encoding="utf-8")
    previous_progress = dict(app_module.回测进度)
    previous_report = dict(app_module.最近多股报告)
    app_module.回测进度.clear()
    app_module.回测进度.update({"run_dir": None, "status": "idle"})
    monkeypatch.setattr(app_module, "实验记录目录", str(tmp_path))
    app_module.最近多股报告.update({"run_dir": str(run)})
    try:
        response = app_module.应用.test_client().get("/api/run-lifecycle")
        assert response.status_code == 200
        assert response.get_json()["run_id"] == "recovered"
    finally:
        app_module.回测进度.clear(); app_module.回测进度.update(previous_progress)
        app_module.最近多股报告.clear(); app_module.最近多股报告.update(previous_report)
