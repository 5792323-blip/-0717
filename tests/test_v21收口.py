import json

import pandas as pd
import subprocess
import sys

from 运行程序.结果生命周期 import 清理可重建深度数据, 锁定
from 运行程序.可信度审计 import 审计运行目录
from 运行程序.基线比较 import 比较


def _manifest(path):
    (path / "运行清单.json").write_text(json.dumps({"run_id": path.name}), encoding="utf-8")


def test_生命周期需要确认且锁定后禁止清理(tmp_path):
    _manifest(tmp_path)
    deep = tmp_path / "回放行情.csv.gz"
    deep.write_text("data")
    try:
        清理可重建深度数据(tmp_path)
        assert False
    except ValueError:
        pass
    锁定(tmp_path)
    try:
        清理可重建深度数据(tmp_path, confirm=True)
        assert False
    except PermissionError:
        pass


def test_审计检测重复成交和缺少核心证据(tmp_path):
    _manifest(tmp_path)
    pd.DataFrame([{"intent_id": "i", "order_id": "o", "execution_id": "e", "前复权成交价": "1", "交易费用": "0"},
                  {"intent_id": "i2", "order_id": "o2", "execution_id": "e", "前复权成交价": "1", "交易费用": "0"}]).to_csv(tmp_path / "交易明细.csv", index=False)
    report = 审计运行目录(tmp_path)
    assert report["overall_status"] == "FAIL"
    assert any(item["check_id"] == "duplicate_execution" and item["status"] == "FAIL" for item in report["checks"])


def test_基线比较兼容成交股数并忽略行顺序(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    left.mkdir(); right.mkdir()
    payload = {"最终权益": 100}
    for path in (left, right):
        (path / "回测结果.json").write_text(json.dumps(payload), encoding="utf-8")
    rows = [{"execution_id": "2", "时间": "2020-01-02", "类型": "买入", "股票代码": "A", "成交股数": 2},
            {"execution_id": "1", "时间": "2020-01-01", "类型": "买入", "股票代码": "A", "成交股数": 1}]
    pd.DataFrame(rows).to_csv(left / "交易明细.csv", index=False)
    pd.DataFrame(list(reversed(rows))).to_csv(right / "交易明细.csv", index=False)
    assert 比较(left, right)["identical"] is True


def test_命令行入口自动生成运行清单和审计(tmp_path):
    output = tmp_path / "result.json"
    subprocess.run([
        sys.executable, "运行程序/run_backtest.py", "--stocks", "600118",
        "--start", "2026-06-01", "--end", "2026-07-03", "--workers", "1",
        "--output", str(output),
    ], check=True, stdout=subprocess.DEVNULL)
    evidence = tmp_path / "result_运行"
    assert (evidence / "运行清单.json").exists()
    assert (evidence / "可信度审计.json").exists()
    manifest = json.loads((evidence / "运行清单.json").read_text())
    assert manifest["run_type"] == "CLI_BACKTEST"
    assert manifest["credibility_status"] in {"PASS", "WARNING", "FAIL"}
