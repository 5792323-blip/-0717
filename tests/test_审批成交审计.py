import json

import pandas as pd

from 运行程序.可信度审计 import 审计运行目录
from 策略引擎.交易账户 import 交易账户


def test_审批成交数量不一致时审计失败(tmp_path):
    (tmp_path / "运行清单.json").write_text(json.dumps({"run_id": "r"}), encoding="utf-8")
    pd.DataFrame([{
        "股票代码": "600519", "结果": "实际成交", "成交股数": 200,
        "成交价": 10, "类型": "买入",
    }]).to_csv(tmp_path / "审批记录.csv", index=False)
    pd.DataFrame([{
        "股票代码": "600519", "intent_id": "i", "order_id": "o",
        "execution_id": "x", "类型": "买入", "成交数量": 100,
        "买入价": 10, "交易费用": 1, "总成本": 1001,
    }]).to_csv(tmp_path / "交易明细.csv", index=False)
    report = 审计运行目录(tmp_path)
    item = next(x for x in report["checks"] if x["check_id"] == "approval_trade_reconciliation")
    assert item["status"] == "FAIL"


def test_成功成交不会生成拒绝编号():
    account = 交易账户(100000)
    view = account.股票视图("600519")
    view.记录审批(类型="买入", 结果="实际成交", 原因="账户批准", 成交股数=100)
    view.记录审批(类型="买入", 结果="组合层拦截", 原因="现金不足", 成交股数=0)
    assert account.审批记录[0]["rejection_id"] is None
    assert account.审批记录[1]["rejection_id"] == "R00000001"


def test_部分成交不会生成拒绝编号():
    account = 交易账户(100000)
    view = account.股票视图("600118")
    view.记录审批(类型="买入", 结果="部分成交", 成交股数=100,
                 成交价=10, 交易费用=1)
    assert account.审批记录[0]["rejection_id"] is None


def test_多股分目录本地生命周期编号按股票作用域审计(tmp_path):
    """不同股票各自从 X00000001 编号，不是重复成交。"""
    (tmp_path / "运行清单.json").write_text(json.dumps({"run_id": "r"}), encoding="utf-8")
    rows = []
    for stock in ("600118", "600519"):
        stock_dir = tmp_path / "股票" / stock
        stock_dir.mkdir(parents=True)
        row = {
            "intent_id": "I00000001", "order_id": "O00000001", "execution_id": "X00000001",
            "类型": "买入", "成交数量": 100, "买入价": 10, "交易费用": 1,
            "总成本": 1001,
        }
        pd.DataFrame([row]).to_csv(stock_dir / "交易明细.csv", index=False)
        rows.append({
            "股票代码": stock, "类型": "买入", "结果": "实际成交", "成交状态": "已成交",
            "成交股数": 100, "成交价": 10, "交易费用": 1,
            "审批前现金": 10000, "审批后现金": 8999,
            "审批前持仓": 0, "审批后持仓": 100,
            "intent_id": "I00000001", "order_id": "O00000001", "execution_id": "X00000001",
        })
    # 交互式多股入口保存的审批事实文件名。
    pd.DataFrame(rows).to_csv(tmp_path / "组合成交审计.csv", index=False)

    report = 审计运行目录(tmp_path)
    checks = {item["check_id"]: item for item in report["checks"]}
    assert checks["duplicate_execution"]["status"] == "PASS"
    assert checks["approval_lifecycle_reconciliation"]["status"] == "PASS"
    assert checks["approval_trade_reconciliation"]["status"] == "PASS"
    manifest = json.loads((tmp_path / "运行清单.json").read_text(encoding="utf-8"))
    assert manifest["credibility_status"] == report["overall_status"]
    assert manifest["can_be_baseline"] is report["can_be_baseline"]


def test_有成交但缺少审批证据不得作为基线(tmp_path):
    (tmp_path / "运行清单.json").write_text(json.dumps({"run_id": "r"}), encoding="utf-8")
    pd.DataFrame([{
        "股票代码": "600519", "intent_id": "i", "order_id": "o", "execution_id": "x",
        "类型": "买入", "成交数量": 100, "买入价": 10, "交易费用": 1, "总成本": 1001,
    }]).to_csv(tmp_path / "交易明细.csv", index=False)
    report = 审计运行目录(tmp_path)
    checks = {item["check_id"]: item for item in report["checks"]}
    assert checks["approval_trade_reconciliation"]["status"] in {"FAIL", "WARNING"}
    assert report["can_be_baseline"] is False


def test_审批逐笔字段错配不得被总量对账掩盖(tmp_path):
    (tmp_path / "运行清单.json").write_text(json.dumps({"run_id": "r"}), encoding="utf-8")
    trades = [{"股票代码": "600118", "intent_id": "i1", "order_id": "o1", "execution_id": "x1",
               "类型": "买入", "成交数量": 100, "买入价": 10, "交易费用": 1, "总成本": 1001},
              {"股票代码": "600519", "intent_id": "i2", "order_id": "o2", "execution_id": "x2",
               "类型": "买入", "成交数量": 100, "买入价": 20, "交易费用": 1, "总成本": 2001}]
    approvals = [{"股票代码": "600519", "类型": "买入", "结果": "实际成交", "成交状态": "已成交", "成交股数": 100,
                  "成交价": 10, "交易费用": 1, "intent_id": "i1", "order_id": "o1", "execution_id": "x1"},
                 {"股票代码": "600118", "类型": "买入", "结果": "实际成交", "成交状态": "已成交", "成交股数": 100,
                  "成交价": 20, "交易费用": 1, "intent_id": "i2", "order_id": "o2", "execution_id": "x2"}]
    pd.DataFrame(trades).to_csv(tmp_path / "交易明细.csv", index=False)
    pd.DataFrame(approvals).to_csv(tmp_path / "审批记录.csv", index=False)
    report = 审计运行目录(tmp_path)
    checks = {item["check_id"]: item for item in report["checks"]}
    assert checks["approval_trade_reconciliation"]["status"] == "FAIL"
    assert checks["approval_lifecycle_reconciliation"]["status"] == "FAIL"


def test_零交易空权益不应显示为可作基线(tmp_path):
    (tmp_path / "运行清单.json").write_text(json.dumps({"run_id": "r"}), encoding="utf-8")
    (tmp_path / "回测结果.json").write_text(json.dumps({"权益曲线": []}), encoding="utf-8")
    report = 审计运行目录(tmp_path)
    checks = {item["check_id"]: item for item in report["checks"]}
    assert checks["cash_conservation"]["status"] == "NOT_RUN"
    assert checks["lookahead"]["status"] == "NOT_RUN"
    assert report["can_be_baseline"] is False


def test_真实部分成交证据逐笔审计通过(tmp_path):
    (tmp_path / "运行清单.json").write_text(json.dumps({"run_id": "partial"}), encoding="utf-8")
    pd.DataFrame([{
        "股票代码": "600519", "intent_id": "i1", "order_id": "o1", "execution_id": "x1",
        "类型": "买入", "成交数量": 40, "买入价": 10, "交易费用": 1, "总成本": 401,
    }]).to_csv(tmp_path / "交易明细.csv", index=False)
    pd.DataFrame([{
        "股票代码": "600519", "intent_id": "i1", "order_id": "o1", "execution_id": "x1",
        "类型": "买入", "结果": "实际成交", "成交状态": "部分成交", "请求股数": 100,
        "成交股数": 40, "成交价": 10, "交易费用": 1,
        "审批前现金": 1000, "审批后现金": 599,
        "审批前持仓": 0, "审批后持仓": 40,
    }]).to_csv(tmp_path / "审批记录.csv", index=False)
    (tmp_path / "回测结果.json").write_text(json.dumps({"权益曲线": [{"权益": 999, "现金": 599, "持仓市值": 400}]}), encoding="utf-8")
    report = 审计运行目录(tmp_path)
    checks = {item["check_id"]: item for item in report["checks"]}
    assert report["overall_status"] == "PASS"
    assert checks["approval_trade_reconciliation"]["status"] == "PASS"
    assert checks["approval_cash_ledger"]["status"] == "PASS"
    assert checks["approval_position_ledger"]["status"] == "PASS"


def test_同时间交易按生命周期编号稳定重建库存(tmp_path):
    (tmp_path / "运行清单.json").write_text(json.dumps({"run_id": "same-time"}), encoding="utf-8")
    trades = [
        {"股票代码": "600519", "intent_id": "i1", "order_id": "o1", "execution_id": "x1",
         "类型": "买入", "成交数量": 100, "买入价": 10, "交易费用": 1, "总成本": 1001,
         "时间": "2025-01-02"},
        {"股票代码": "600519", "intent_id": "i2", "order_id": "o2", "execution_id": "x2",
         "类型": "卖出", "成交数量": 100, "卖出价": 11, "交易费用": 1, "卖出净金额": 1099,
         "时间": "2025-01-02"},
    ]
    pd.DataFrame(list(reversed(trades))).to_csv(tmp_path / "交易明细.csv", index=False)
    report = 审计运行目录(tmp_path)
    checks = {item["check_id"]: item for item in report["checks"]}
    assert checks["trade_ledger"]["status"] == "PASS"
