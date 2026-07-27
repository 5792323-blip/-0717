#!/usr/bin/env python3
"""RSI与MACD、KDJ、成交量的多信号共振过滤。"""

import math

import numpy as np
import pandas as pd


def _cache(state):
    return state.setdefault("rsi_resonance_filter", {
        "bars": [], "指标": {}, "样本数": 0,
    })


def _指标(cache, config):
    bars = cache["bars"]
    if len(bars) < max(35, int(config.get("KDJ周期", 9))):
        return {}
    close = pd.Series([x["close"] for x in bars], dtype="float64")
    high = pd.Series([x["high"] for x in bars], dtype="float64")
    low = pd.Series([x["low"] for x in bars], dtype="float64")
    volume = pd.Series([x["volume"] for x in bars], dtype="float64")
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    period = int(config.get("KDJ周期", 9))
    lowest = low.rolling(period).min()
    highest = high.rolling(period).max()
    rsv = ((close - lowest) / (highest - lowest).replace(0, np.nan) * 100).fillna(50)
    k = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    d = k.ewm(alpha=1 / 3, adjust=False).mean()
    vol_period = int(config.get("成交量均线周期", 20))
    vol_ma = volume.rolling(vol_period).mean()
    return {
        "MACD_DIF": float(dif.iloc[-1]), "MACD_DEA": float(dea.iloc[-1]),
        "MACD金叉": bool(dif.iloc[-1] > dea.iloc[-1] and dif.iloc[-2] <= dea.iloc[-2]),
        "MACD多头": bool(dif.iloc[-1] > dea.iloc[-1]),
        "KDJ_K": float(k.iloc[-1]), "KDJ_D": float(d.iloc[-1]),
        "KDJ金叉": bool(k.iloc[-1] > d.iloc[-1] and k.iloc[-2] <= d.iloc[-2]),
        "KDJ多头": bool(k.iloc[-1] > d.iloc[-1]),
        "量比": float(volume.iloc[-1] / vol_ma.iloc[-1]) if vol_ma.iloc[-1] > 0 else None,
    }


def 更新(K线数据, 状态, 配置):
    cache = _cache(状态)
    date = str(K线数据.get("日期", ""))[:10]
    if not date:
        return
    if cache.get("当前日期") == date:
        return
    cache["当前日期"] = date
    try:
        cache["bars"].append({
            "close": float(K线数据.get("前复权_收盘", 0)),
            "high": float(K线数据.get("前复权_最高", 0)),
            "low": float(K线数据.get("前复权_最低", 0)),
            "volume": float(K线数据.get("成交量", 0) or 0),
        })
        cache["bars"] = cache["bars"][-160:]
        cache["指标"] = _指标(cache, 配置)
        cache["样本数"] = len(cache["bars"])
    except (TypeError, ValueError):
        cache["指标"] = {}


def 获取状态(状态, 配置):
    cache = _cache(状态)
    return {"指标": cache.get("指标", {}), "样本数": cache.get("样本数", 0)}


def 检查(哨兵价类型, K线数据, 状态, 配置):
    cache = _cache(状态)
    metrics = cache.get("指标", {})
    if not metrics:
        passed = bool(配置.get("历史不足时放行", False))
        return {"通过": passed, "原因": "MACD/KDJ历史不足" + ("，放行" if passed else "，拦截")}
    volume_ratio = metrics.get("量比")
    need_volume = bool(配置.get("要求成交量确认", True))
    checks = {
        "MACD": metrics.get("MACD多头", False),
        "KDJ": metrics.get("KDJ多头", False),
        "成交量": (volume_ratio is not None and volume_ratio >= float(配置.get("最低量比", 1.0)))
        if need_volume else True,
    }
    required = max(1, int(配置.get("最少通过数量", 2)))
    passed = sum(checks.values()) >= required
    return {
        "通过": passed,
        "原因": f"共振{sum(checks.values())}/{len(checks)}，需{required}",
        "共振明细": checks, "量比": volume_ratio,
    }
