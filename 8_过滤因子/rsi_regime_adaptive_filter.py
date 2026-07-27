#!/usr/bin/env python3
"""根据前一根完成K线的趋势状态调整RSI信号允许范围。"""

import pandas as pd


def _cache(state):
    return state.setdefault("rsi_regime_adaptive_filter", {"closes": [], "状态": "历史不足"})


def 更新(K线数据, 状态, 配置):
    cache = _cache(状态)
    date = str(K线数据.get("日期", ""))[:10]
    if not date or cache.get("当前日期") == date:
        return
    cache["当前日期"] = date
    try:
        cache["closes"].append(float(K线数据.get("前复权_收盘", 0)))
        cache["closes"] = cache["closes"][-160:]
    except (TypeError, ValueError):
        return
    closes = pd.Series(cache["closes"], dtype="float64")
    fast = int(配置.get("短均线周期", 20))
    slow = int(配置.get("长均线周期", 60))
    if len(closes) < slow + 5:
        cache["状态"] = "历史不足"
        return
    fast_ma = closes.rolling(fast).mean().iloc[-1]
    slow_ma = closes.rolling(slow).mean().iloc[-1]
    prior_fast = closes.rolling(fast).mean().iloc[-6]
    if fast_ma > slow_ma and fast_ma > prior_fast:
        cache["状态"] = "牛市"
    elif fast_ma < slow_ma and fast_ma < prior_fast:
        cache["状态"] = "熊市"
    else:
        cache["状态"] = "震荡市"


def 获取状态(状态, 配置):
    cache = _cache(状态)
    return {"状态": cache.get("状态", "历史不足")}


def 获取RSI阈值(信号类型, 状态, 配置):
    """Return the regime-specific target while keeping the original signal name."""
    fixed = {"RSI上穿20": 20, "RSI上穿30": 30, "RSI上穿70": 70, "RSI上穿80": 80}
    if 信号类型 not in fixed or 配置.get("阈值模式", "fixed") != "adaptive":
        return fixed.get(信号类型)
    regime = _cache(状态).get("状态", "历史不足")
    mapping = 配置.get("状态阈值", {}).get(regime, {})
    return float(mapping.get(信号类型, fixed[信号类型]))


def 检查(哨兵价类型, K线数据, 状态, 配置):
    regime = _cache(状态).get("状态", "历史不足")
    if regime == "历史不足":
        passed = bool(配置.get("历史不足时放行", False))
        return {"通过": passed, "原因": "RSI市场状态历史不足" + ("，放行" if passed else "，拦截"), "状态": regime}
    allowed = 配置.get({"牛市": "牛市允许信号", "熊市": "熊市允许信号", "震荡市": "震荡市允许信号"}[regime], [])
    passed = not allowed or 哨兵价类型 in allowed
    return {"通过": passed, "原因": f"{regime}允许信号={','.join(allowed) if allowed else '全部'}", "状态": regime}
