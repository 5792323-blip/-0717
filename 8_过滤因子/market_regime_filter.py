#!/usr/bin/env python3
"""基于沪深300前一交易日状态的横截面市场环境过滤。"""

import os

import numpy as np
import pandas as pd


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _加载(状态, 配置):
    cache = 状态.setdefault("market_regime_filter", {})
    if "数据" not in cache:
        path = os.path.join(项目根目录, "数据模块", "大盘数据", "hs300_日K线.pkl")
        if not os.path.exists(path):
            cache["数据"] = pd.DataFrame()
        else:
            data = pd.read_pickle(path).copy()
            data["date"] = pd.to_datetime(data["date"]).dt.normalize()
            data = data.sort_values("date").drop_duplicates("date")
            data["ma20"] = data["close"].rolling(20, min_periods=20).mean()
            data["ma60"] = data["close"].rolling(60, min_periods=60).mean()
            data["ma20_slope"] = data["ma20"].diff(5)
            data["realized_vol"] = data["close"].pct_change(fill_method=None).rolling(20, min_periods=20).std(ddof=0)
            data["vol_baseline"] = data["realized_vol"].rolling(60, min_periods=30).mean()
            cache["数据"] = data
        cache["当前日期"] = None
        cache["状态"] = "历史不足"
        cache["明细"] = {}
    return cache


def _计算状态(cache, date, config):
    data = cache.get("数据", pd.DataFrame())
    if data.empty:
        return "历史不足", {"原因": "缺少HS300数据"}
    current_date = pd.Timestamp(str(date)[:10]).normalize()
    # 严格使用当前交易日前的数据，不能读取当日指数收盘。
    history = data[data["date"] < current_date]
    if history.empty:
        return "历史不足", {"原因": "没有前一交易日指数数据"}
    row = history.iloc[-1]
    if pd.isna(row.get("ma20")) or pd.isna(row.get("ma60")) or pd.isna(row.get("ma20_slope")):
        return "历史不足", {"原因": "指数均线历史不足"}
    high_vol_ratio = float(config.get("高波动比率", 1.5))
    vol = row.get("realized_vol")
    baseline = row.get("vol_baseline")
    if pd.notna(vol) and pd.notna(baseline) and baseline > 0 and vol > baseline * high_vol_ratio:
        regime = "收缩模式"
    elif row["close"] > row["ma60"] and row["ma20_slope"] > 0:
        regime = "进攻模式"
    elif row["close"] < row["ma60"] and row["ma20_slope"] < 0:
        regime = "防守模式"
    else:
        regime = "震荡模式"
    return regime, {
        "指数日期": str(row["date"].date()),
        "状态": regime,
        "指数收盘": float(row["close"]),
        "MA20": float(row["ma20"]),
        "MA60": float(row["ma60"]),
        "MA20斜率": float(row["ma20_slope"]),
        "实现波动率": float(vol) if pd.notna(vol) else None,
        "波动率基准": float(baseline) if pd.notna(baseline) else None,
    }


def 更新(K线数据, 状态, 配置):
    cache = _加载(状态, 配置)
    date = str(K线数据.get("日期", ""))[:10]
    if not date:
        return
    cache["当前日期"] = date
    cache["状态"], cache["明细"] = _计算状态(cache, date, 配置)


def 获取状态(状态, 配置):
    cache = _加载(状态, 配置)
    return {"状态": cache.get("状态", "历史不足"), "明细": cache.get("明细", {})}


def 检查(哨兵价类型, K线数据, 状态, 配置):
    cache = _加载(状态, 配置)
    regime = cache.get("状态", "历史不足")
    if regime == "历史不足":
        passed = bool(配置.get("历史不足时放行", True))
        return {"通过": passed, "原因": "市场状态历史不足", "状态": regime}
    allowed = 配置.get(f"{regime}允许信号")
    blocked = 配置.get(f"{regime}禁止信号")
    if allowed:
        passed = 哨兵价类型 in allowed
        reason = f"{regime}允许={','.join(allowed)}"
    elif blocked:
        passed = 哨兵价类型 not in blocked
        reason = f"{regime}禁止={','.join(blocked)}"
    else:
        passed = True
        reason = f"{regime}放行"
    return {"通过": passed, "原因": reason, "状态": regime, "状态明细": cache.get("明细", {})}
