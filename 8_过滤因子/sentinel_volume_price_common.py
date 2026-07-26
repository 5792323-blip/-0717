"""哨兵形成前的量价证据读取与独立拦截条件。"""

import math


def 数值(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def 范围值(value, fallback):
    value = 数值(value)
    return fallback if value is None else value


def _适用信号(哨兵价类型, 配置):
    signals = 配置.get("适用信号", []) or []
    return not signals or 哨兵价类型 in signals


def _历史不足结果(snapshot, 配置):
    allow = bool(配置.get("历史不足时放行", True))
    return {
        "通过": allow,
        "原因": "哨兵形成前量价历史不足，" + ("放行" if allow else "拦截"),
        "快照": snapshot,
    }


def 检查哨兵量价条件(哨兵价类型, 状态, 配置, condition):
    """执行一个独立的哨兵量价交易拦截因子。"""
    if not _适用信号(哨兵价类型, 配置):
        return {"通过": True, "原因": f"{哨兵价类型}不在适用信号范围", "适用": False}

    snapshot = 状态.get("哨兵量价快照") or {}
    if not snapshot.get("有效", False):
        return _历史不足结果(snapshot, 配置)

    relative_volume = 数值(snapshot.get("相对量能"))
    dryup_ratio = 数值(snapshot.get("缩量比例"))
    price_change = 数值(snapshot.get("近期价格变化"))
    trend_gain = 数值(snapshot.get("趋势涨幅"))
    close_strength = 数值(snapshot.get("收盘强度"))
    upper_shadow = 数值(snapshot.get("上影比例"))
    single_bar_drop = 数值(snapshot.get("单根跌幅"))

    if condition == "dryup":
        maximum = 范围值(配置.get("缩量比例上限"), 0.85)
        passed = price_change is not None and price_change < 0 and dryup_ratio is not None and dryup_ratio <= maximum
        reason = f"近期价格变化={price_change!s}，缩量比例={dryup_ratio!s}，要求回撤且≤{maximum:.3f}"
    elif condition == "price_strength":
        minimum_gain = 范围值(配置.get("近期价格涨幅下限"), 0.0)
        minimum_volume = 范围值(配置.get("相对量能下限"), 1.10)
        passed = (price_change is not None and price_change >= minimum_gain
                  and relative_volume is not None and relative_volume >= minimum_volume)
        reason = f"近期涨幅={price_change!s}，相对量能={relative_volume!s}，要求≥{minimum_gain:.3f}/≥{minimum_volume:.3f}"
    elif condition == "volume_trend":
        minimum_gain = 范围值(配置.get("趋势涨幅下限"), 0.0)
        minimum_volume = 范围值(配置.get("相对量能下限"), 1.10)
        passed = (trend_gain is not None and trend_gain >= minimum_gain
                  and relative_volume is not None and relative_volume >= minimum_volume)
        reason = f"趋势涨幅={trend_gain!s}，相对量能={relative_volume!s}，要求≥{minimum_gain:.3f}/≥{minimum_volume:.3f}"
    elif condition == "close_strength":
        minimum = 范围值(配置.get("最低收盘强度"), 0.60)
        passed = close_strength is not None and close_strength >= minimum
        reason = f"收盘强度={close_strength!s}，要求≥{minimum:.3f}"
    elif condition == "upper_shadow":
        maximum = 范围值(配置.get("最大上影比例"), 0.35)
        passed = upper_shadow is not None and upper_shadow <= maximum
        reason = f"上影比例={upper_shadow!s}，要求≤{maximum:.3f}"
    elif condition == "volume_drop":
        drop = 范围值(配置.get("异常跌幅阈值"), -0.02)
        volume = 范围值(配置.get("异常量能阈值"), 1.50)
        close = 范围值(配置.get("异常收盘强度上限"), 0.35)
        failed_pattern = (single_bar_drop is not None and single_bar_drop <= drop
                          and relative_volume is not None and relative_volume >= volume
                          and close_strength is not None and close_strength <= close)
        passed = not failed_pattern
        reason = f"单根跌幅={single_bar_drop!s}，相对量能={relative_volume!s}，收盘强度={close_strength!s}"
    else:  # pragma: no cover - 仅供受控的独立模块调用
        raise ValueError(f"未知哨兵量价条件: {condition}")

    return {
        "通过": passed,
        "原因": reason + ("，通过" if passed else "，拦截"),
        "适用": True,
        "快照": snapshot,
    }
