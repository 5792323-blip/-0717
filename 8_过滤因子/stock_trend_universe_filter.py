#!/usr/bin/env python3
"""个股大周期趋势准入：只影响新开仓，避免在长期下跌中接飞刀。"""

import pandas as pd


def _cache(state):
    return state.setdefault("stock_trend_universe_filter", {
        "bars": [], "指标": {}, "状态": "历史不足",
    })


def 更新(kline, state, config):
    cache = _cache(state)
    date = str(kline.get("日期", ""))[:10]
    if not date or cache.get("当前日期") == date:
        return
    cache["当前日期"] = date
    try:
        cache["bars"].append({
            "close": float(kline.get("前复权_收盘", 0)),
        })
        cache["bars"] = cache["bars"][-240:]
        closes = pd.Series([row["close"] for row in cache["bars"]], dtype="float64")
        fast_period = int(config.get("短均线周期", 20))
        slow_period = int(config.get("中均线周期", 60))
        long_period = int(config.get("长均线周期", 120))
        slope_period = int(config.get("长均线斜率周期", 20))
        if len(closes) < max(long_period + slope_period, 2):
            cache["状态"] = "历史不足"
            cache["指标"] = {}
            return
        fast = closes.rolling(fast_period).mean()
        slow = closes.rolling(slow_period).mean()
        long_ma = closes.rolling(long_period).mean()
        recent_high = closes.rolling(slow_period).max().iloc[-1]
        long_slope = long_ma.iloc[-1] / long_ma.iloc[-1 - slope_period] - 1
        cache["指标"] = {
            "收盘": float(closes.iloc[-1]),
            "短均线": float(fast.iloc[-1]),
            "中均线": float(slow.iloc[-1]),
            "长均线": float(long_ma.iloc[-1]),
            "长均线斜率": float(long_slope),
            "中期高点回撤": float(closes.iloc[-1] / recent_high - 1) if recent_high > 0 else None,
        }
        cache["状态"] = "可交易"
    except (TypeError, ValueError, ZeroDivisionError):
        cache["状态"] = "数据异常"
        cache["指标"] = {}


def 获取状态(state, config):
    cache = _cache(state)
    return {"状态": cache.get("状态", "历史不足"), "指标": cache.get("指标", {})}


def 检查(signal_type, kline, state, config):
    # Existing positions are managed by exit/grid rules and are not forced out here.
    if state.get("已有持仓"):
        return {"通过": True, "原因": "已有持仓：趋势准入不强制平仓", "状态": "持仓豁免"}
    cache = _cache(state)
    if cache.get("状态") != "可交易":
        passed = bool(config.get("历史不足时放行", False))
        return {"通过": passed, "原因": "个股趋势历史不足或数据异常", "状态": cache.get("状态")}
    metrics = cache.get("指标", {})
    close = metrics["收盘"]
    long_ma = metrics["长均线"]
    fast = metrics["短均线"]
    slow = metrics["中均线"]
    long_slope = metrics["长均线斜率"]
    drawdown = metrics["中期高点回撤"]
    below_long_limit = float(config.get("长均线下偏离上限", 0.10))
    fast_slow_limit = float(config.get("短中均线偏离上限", 0.05))
    slope_limit = float(config.get("长均线斜率下限", -0.02))
    drawdown_limit = float(config.get("中期高点回撤上限", 0.25))
    if bool(config.get("分级风险模式", False)):
        extreme_below = float(config.get("极端长均线下偏离上限", 0.20))
        extreme_drawdown = float(config.get("极端中期回撤上限", 0.45))
        extreme_slope = float(config.get("极端斜率下限", -0.05))
        extreme = (
            close < long_ma * (1 - extreme_below)
            or (drawdown is not None and drawdown < -extreme_drawdown
                and long_slope < extreme_slope)
        )
        if extreme:
            return {"通过": False, "原因": "极端趋势风险，禁止新开仓",
                    "状态": "极端风险", "指标": metrics}
        weak = (
            close < long_ma * (1 - below_long_limit)
            or (fast < slow * (1 - fast_slow_limit) and long_slope < slope_limit)
            or (drawdown is not None and drawdown < -drawdown_limit and long_slope < 0)
        )
        if weak:
            allowed = config.get("风险状态允许信号", ["RSI上穿20"])
            passed = signal_type in allowed
            return {"通过": passed, "原因": "风险状态仅允许" + ",".join(allowed),
                    "状态": "风险状态", "指标": metrics}
    reasons = []
    if close < long_ma * (1 - below_long_limit):
        reasons.append("收盘低于长均线过多")
    if fast < slow * (1 - fast_slow_limit) and long_slope < slope_limit:
        reasons.append("短中均线同步走弱")
    if drawdown is not None and drawdown < -drawdown_limit and long_slope < 0:
        reasons.append("中期高点回撤过大")
    passed = not reasons
    return {
        "通过": passed,
        "原因": "趋势准入通过" if passed else "；".join(reasons),
        "状态": "可交易" if passed else "趋势走坏",
        "指标": metrics,
    }
