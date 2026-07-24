#!/usr/bin/env python3
"""基于前一交易日完成数据的波动率状态过滤。"""

import numpy as np
import pandas as pd


def _缓存(状态, 配置):
    cache = 状态.setdefault("volatility_regime_filter", {})
    if "历史日线" not in cache:
        cache.update({
            "历史日线": [], "当前日": None, "当日K线": None,
            "分类": None, "波动率": None, "样本数": 0,
        })
    return cache


def _完成日线(cache, 配置):
    daily = cache.get("当日K线")
    if not daily:
        return
    cache["历史日线"].append(daily)
    period = max(2, int(配置.get("计算周期", 20)))
    cache["历史日线"] = cache["历史日线"][-(period + 1):]
    closes = pd.Series([item["close"] for item in cache["历史日线"]], dtype="float64")
    returns = closes.pct_change(fill_method=None).dropna()
    recent = returns.tail(period)
    cache["样本数"] = int(len(recent))
    if len(recent) < max(10, period // 2):
        cache["分类"] = None
        cache["波动率"] = None
        return
    volatility = float(recent.std(ddof=0))
    cache["波动率"] = volatility
    high = float(配置.get("高波动阈值", 0.03))
    low = float(配置.get("低波动阈值", 0.015))
    if volatility >= high:
        cache["分类"] = "高波动"
    elif volatility <= low:
        cache["分类"] = "低波动"
    else:
        cache["分类"] = "中波动"


def 更新(K线数据, 状态, 配置):
    cache = _缓存(状态, 配置)
    date = str(K线数据.get("日期", ""))[:10]
    if not date:
        return
    if cache["当前日"] != date:
        _完成日线(cache, 配置)
        cache["当前日"] = date
        cache["当日K线"] = None
    bar = {
        "date": pd.Timestamp(date),
        "open": float(K线数据.get("前复权_开盘", np.nan)),
        "high": float(K线数据.get("前复权_最高", np.nan)),
        "low": float(K线数据.get("前复权_最低", np.nan)),
        "close": float(K线数据.get("前复权_收盘", np.nan)),
        "volume": float(K线数据.get("成交量", 0) or 0),
    }
    if cache["当日K线"] is None:
        cache["当日K线"] = bar
    else:
        daily = cache["当日K线"]
        daily["high"] = max(daily["high"], bar["high"])
        daily["low"] = min(daily["low"], bar["low"])
        daily["close"] = bar["close"]
        daily["volume"] += bar["volume"]


def 获取状态(状态, 配置):
    cache = _缓存(状态, 配置)
    return {
        "分类": cache.get("分类"),
        "波动率": cache.get("波动率"),
        "样本数": cache.get("样本数", 0),
    }


def 检查(哨兵价类型, K线数据, 状态, 配置):
    cache = _缓存(状态, 配置)
    regime = cache.get("分类")
    if regime is None:
        return {
            "通过": bool(配置.get("历史不足时放行", True)),
            "原因": "波动率历史不足，放行" if 配置.get("历史不足时放行", True) else "波动率历史不足，拦截",
            "状态": "历史不足",
        }
    allowed = 配置.get(f"{regime}允许信号")
    blocked = 配置.get(f"{regime}禁止信号")
    if allowed:
        passed = 哨兵价类型 in allowed
        reason = f"{regime}，允许信号={','.join(allowed)}"
    elif blocked:
        passed = 哨兵价类型 not in blocked
        reason = f"{regime}，禁止信号={','.join(blocked)}"
    else:
        passed = True
        reason = f"{regime}，未配置信号拦截"
    return {
        "通过": passed,
        "原因": reason,
        "状态": regime,
        "波动率": cache.get("波动率"),
        "样本数": cache.get("样本数", 0),
    }
