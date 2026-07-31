import json

import pandas as pd

from 运行程序.实验身份 import 生成实验身份
from 运行程序.可信度审计 import 审计运行目录


def test_cli与页面相同实验身份一致且费用账户模式敏感():
    base = dict(
        code_version="code-a", config_hash="config-a", data_version="data-a",
        universe_version="universe-a", stocks=["600519", "000001"],
        start_date="2020-01-01", end_date="2020-12-31",
        fee_config={"commission": 0.00025}, account_mode="shared",
    )
    assert 生成实验身份(**base) == 生成实验身份(**base)
    assert 生成实验身份(**{**base, "fee_config": {"commission": 0.0003}}) != 生成实验身份(**base)
    assert 生成实验身份(**{**base, "account_mode": "independent"}) != 生成实验身份(**base)


def test审计按股票作用域区分本地生命周期编号():
    root = __import__("pathlib").Path(__file__).parent / "_tmp_audit_identity"
    root.mkdir(exist_ok=True)
    (root / "运行清单.json").write_text(json.dumps({"run_id": "r"}), encoding="utf-8")
    rows = []
    for stock in ("600118", "600519"):
        path = root / "股票" / stock
        path.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([{
            "intent_id": "I00000001", "order_id": "O00000001", "execution_id": "X00000001",
            "类型": "买入", "成交数量": 100, "买入价": 10, "交易费用": 1, "总成本": 1001,
        }]).to_csv(path / "交易明细.csv", index=False)
        rows.append({
            "股票代码": stock, "类型": "买入", "结果": "实际成交", "成交状态": "已成交",
            "成交股数": 100, "成交价": 10, "交易费用": 1, "审批前现金": 10000,
            "审批后现金": 8999, "审批前持仓": 0, "审批后持仓": 100,
            "intent_id": "I00000001", "order_id": "O00000001", "execution_id": "X00000001",
        })
    pd.DataFrame(rows).to_csv(root / "组合成交审计.csv", index=False)
    report = 审计运行目录(root)
    assert next(x for x in report["checks"] if x["check_id"] == "duplicate_execution")["status"] == "PASS"
