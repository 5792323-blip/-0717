"""Phase 2 资金预算审批与新旧审批对账数据结构。"""

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class 预算审批:
    approval_id: str
    intent_id: str
    symbol: str
    status: str
    requested_budget: Optional[float]
    approved_budget: float
    exposure_before: Optional[float] = None
    projected_exposure_after: Optional[float] = None
    rejection_reason: Optional[str] = None
    constraint_hits: Tuple[str, ...] = ()
    decision_snapshot_id: Optional[str] = None
    approved_at: Optional[str] = None


@dataclass(frozen=True)
class 审批对账:
    trade_date: str
    intent_id: str
    symbol: str
    legacy_status: str
    legacy_budget: Optional[float]
    legacy_quantity: Optional[int]
    shadow_status: str
    shadow_budget: Optional[float]
    shadow_quantity: Optional[int]
    difference_type: Optional[str]
    difference_amount: float
    explained: bool
    explanation: Optional[str] = None
    metadata: dict = field(default_factory=dict)

