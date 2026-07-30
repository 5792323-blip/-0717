"""生成逐笔交易和账户曲线的稳定指纹，用于迁移前后对账。"""

import hashlib
import json


def _标准值(value):
    if hasattr(value, "item"):
        try:
            return _标准值(value.item())
        except (ValueError, TypeError):
            pass
    if isinstance(value, float):
        return round(value, 10)
    if isinstance(value, dict):
        return {str(key): _标准值(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_标准值(item) for item in value]
    return value


def 生成指纹(records):
    """对记录列表生成与字典顺序无关的SHA256指纹。"""
    payload = json.dumps(_标准值(list(records)), ensure_ascii=False,
                         sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def 交易指纹(交易明细):
    if 交易明细 is None:
        return 生成指纹([])
    columns = [
        column for column in (
            "时间", "类型", "成交数量", "买入价", "卖出价", "交易费用",
            "总成本", "成交净额", "盈亏比例", "持仓组ID",
        ) if column in 交易明细.columns
    ]
    return 生成指纹(交易明细[columns].to_dict("records"))


def 账户曲线指纹(曲线):
    if 曲线 is None:
        return 生成指纹([])
    fields = [column for column in ("日期", "现金", "持仓市值", "权益", "持仓数量")
              if column in 曲线.columns]
    return 生成指纹(曲线[fields].to_dict("records"))


def 结果指纹(交易明细, 账户曲线, 最终权益):
    return {
        "trade_hash": 交易指纹(交易明细),
        "daily_account_hash": 账户曲线指纹(账户曲线),
        "final_equity_hash": 生成指纹([float(最终权益)]),
    }

