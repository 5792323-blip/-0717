# atr_protective_stop.py — ATR亏损保护止损
#
# 与 atr_take_profit 分离：本模块只负责保护浮亏仓位，盈利跟踪止盈仍由
# 原有模块负责。默认关闭，由卖出规则配置控制。


def 检查(持仓盈亏比例, 当前ATR, 买入价, ATR倍数=2.0, **kwargs):
    """按首次/当前持仓成本下方的 ATR 距离生成保护止损线。"""
    try:
        买入价 = float(买入价)
        当前ATR = float(当前ATR)
        盈亏 = float(持仓盈亏比例)
        倍数 = float(ATR倍数)
    except (TypeError, ValueError):
        return {"触发": False, "原因": "缺少有效价格、ATR或盈亏数据"}

    if 买入价 <= 0 or 当前ATR <= 0 or 倍数 <= 0:
        return {"触发": False, "原因": "价格、ATR或ATR倍数无效"}

    止损价 = 买入价 - 倍数 * 当前ATR
    止损比例 = (买入价 - 止损价) / 买入价
    触发 = 盈亏 <= -止损比例
    return {
        "触发": 触发,
        "原因": (
            f"ATR亏损保护: 当前净盈亏{盈亏:.2%}，止损线{止损价:.2f} "
            f"({倍数:.1f}×ATR={止损比例:.2%})"
        ),
        "止损价": 止损价,
        "ATR倍数": 倍数,
    }
