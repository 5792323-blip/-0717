"""第一阶段标准数据结构。

这些对象只描述事实和意图，不负责修改交易账户。
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class 决策快照:
    snapshot_id: str
    run_id: str
    account_id: str
    asof_date: str
    available_at: str
    effective_date: str
    market_state: str
    market_score: Optional[float]
    allow_new_entries: bool
    target_exposure: float
    hard_exposure_cap: float
    max_positions: int
    per_stock_cap: float
    cash_floor: float
    universe_version: str = ""
    feature_version: str = ""
    calculation_version: str = ""
    config_hash: str = ""
    mode: str = "SHADOW"


@dataclass(frozen=True)
class 订单意图:
    intent_id: str
    strategy_id: str
    symbol: str
    side: str
    signal_date: str
    submitted_at: str
    signal_type: str
    primary_reason: str
    secondary_reasons: Tuple[str, ...] = ()
    requested_budget: Optional[float] = None
    requested_quantity: Optional[int] = None
    priority_score: Optional[float] = None
    decision_snapshot_id: Optional[str] = None
    sentinel_state_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class 可执行订单:
    order_id: str
    intent_id: str
    approval_id: Optional[str]
    symbol: str
    side: str
    quantity: int
    order_type: str
    submitted_date: str
    earliest_execution_time: str
    max_budget: Optional[float] = None
    limit_price: Optional[float] = None
    primary_reason: str = ""
    secondary_reasons: Tuple[str, ...] = ()


@dataclass(frozen=True)
class 成交结果:
    execution_id: str
    order_id: str
    intent_id: str
    symbol: str
    side: str
    status: str
    requested_quantity: int
    filled_quantity: int
    execution_price: Optional[float]
    gross_amount: float
    commission: float
    stamp_tax: float
    slippage_cost: float
    net_cash_change: float
    execution_time: Optional[str]
    failure_reason: Optional[str] = None
    source: str = "LEGACY_ADAPTER"
    account_applied: bool = False


@dataclass(frozen=True)
class 账户变化:
    event_id: str
    run_id: str
    account_id: str
    event_sequence: int
    trade_date: str
    symbol: str
    event_type: str
    cash_before: float
    cash_after: float
    position_before: int
    position_after: int
    net_cash_change: float
    intent_id: Optional[str] = None
    order_id: Optional[str] = None
    execution_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def 转为字典(value: Any) -> Dict[str, Any]:
    """将标准数据结构转为可写入JSON的字典。"""
    result = asdict(value)
    return result

