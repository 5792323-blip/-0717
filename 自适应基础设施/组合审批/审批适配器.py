"""将现有账户审批记录转换为标准审批并运行旁路对账。

本模块只读取记录，不读取或修改账户，不参与正式成交。
"""

from 自适应基础设施.标识管理.事件编号 import 生成编号
from 自适应基础设施.数据结构.预算审批 import 审批对账, 预算审批


def _数值(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _整数(value, default=None):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def 映射旧审批(row, run_id, account_id, sequence):
    symbol = str(row.get("股票代码", ""))
    trade_date = str(row.get("时间", row.get("日期", "")))
    intent_id = 生成编号("intent", run_id, account_id, symbol, sequence)
    approval_id = 生成编号("approval", intent_id)
    quantity = _整数(row.get("请求股数"), 0) or 0
    filled = _整数(row.get("成交股数"), 0) or 0
    price = _数值(row.get("成交价"), 0.0) or 0.0
    requested_budget = quantity * price if quantity and price else None
    approved_budget = filled * price if filled and price else 0.0
    status = "APPROVED" if filled == quantity and filled > 0 else (
        "PARTIALLY_APPROVED" if filled > 0 else "REJECTED"
    )
    legacy_result = str(row.get("结果", ""))
    constraints = []
    reason = str(row.get("原因", "") or "")
    if "现金" in reason:
        constraints.append("CASH_FLOOR")
    if "仓位" in reason:
        constraints.append("POSITION_LIMIT")
    if "最大持仓" in reason:
        constraints.append("MAX_POSITIONS")
    approval = 预算审批(
        approval_id=approval_id, intent_id=intent_id, symbol=symbol,
        status=status, requested_budget=requested_budget,
        approved_budget=approved_budget,
        rejection_reason=reason if status == "REJECTED" else None,
        constraint_hits=tuple(constraints), approved_at=trade_date,
    )
    return approval, {
        "交易日期": trade_date, "旧结果": legacy_result,
        "请求股数": quantity, "成交股数": filled, "成交价": price,
        "原因": reason, "股票代码": symbol, "intent_id": intent_id,
    }


def 影子对账(row, run_id, account_id, sequence):
    approval, legacy = 映射旧审批(row, run_id, account_id, sequence)
    legacy_status = "APPROVED" if legacy["旧结果"] == "实际成交" and legacy["成交股数"] == legacy["请求股数"] else (
        "PARTIALLY_APPROVED" if legacy["成交股数"] > 0 else "REJECTED"
    )
    # 首版Shadow只验证标准化映射是否保留旧审批事实，不能声称已接管审批。
    same = legacy_status == approval.status and abs(
        approval.approved_budget - legacy["成交股数"] * legacy["成交价"]
    ) < 1e-6
    difference = None if same else "MAPPING_DIFFERENCE"
    reconciliation = 审批对账(
        trade_date=legacy["交易日期"], intent_id=approval.intent_id,
        symbol=approval.symbol, legacy_status=legacy_status,
        legacy_budget=approval.requested_budget,
        legacy_quantity=legacy["请求股数"], shadow_status=approval.status,
        shadow_budget=approval.approved_budget,
        shadow_quantity=legacy["成交股数"], difference_type=difference,
        difference_amount=0.0 if same else 1.0, explained=same,
        explanation="标准化映射与旧审批结果一致" if same else "需要人工检查",
    )
    return approval, reconciliation

