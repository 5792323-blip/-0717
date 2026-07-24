#!/usr/bin/env python3
"""只在前一交易日沪深300收盘位于长期均线上方时允许开仓。"""

import os

import pandas as pd


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _加载(状态, 配置):
    period = int(配置.get("均线周期", 120))
    root = 状态.setdefault("index_trend_filter", {})
    cache = root.setdefault(period, {})
    if "数据" not in cache:
        path = os.path.join(项目根目录, "数据模块", "大盘数据", "hs300_日K线.pkl")
        if not os.path.exists(path):
            cache["数据"] = pd.DataFrame()
        else:
            data = pd.read_pickle(path).copy()
            data["date"] = pd.to_datetime(data["date"]).dt.normalize()
            data = data.sort_values("date").drop_duplicates("date")
            data["trend_ma"] = data["close"].rolling(period, min_periods=period).mean()
            cache["数据"] = data
        cache["状态"] = "历史不足"
        cache["明细"] = {}
    return cache


def _计算状态(cache, date):
    data = cache.get("数据", pd.DataFrame())
    if data.empty:
        return "历史不足", {"原因": "缺少HS300数据"}
    current_date = pd.Timestamp(str(date)[:10]).normalize()
    # 只能使用当前股票交易日前已经完成的指数日线。
    history = data[data["date"] < current_date]
    if history.empty:
        return "历史不足", {"原因": "没有前一交易日指数数据"}
    row = history.iloc[-1]
    if pd.isna(row.get("trend_ma")):
        return "历史不足", {"原因": "指数均线历史不足"}
    risk_on = float(row["close"]) > float(row["trend_ma"])
    return ("风险开启" if risk_on else "风险关闭"), {
        "指数日期": str(row["date"].date()),
        "指数收盘": float(row["close"]),
        "趋势均线": float(row["trend_ma"]),
    }


def 更新(K线数据, 状态, 配置):
    cache = _加载(状态, 配置)
    date = str(K线数据.get("日期", ""))[:10]
    if date:
        cache["状态"], cache["明细"] = _计算状态(cache, date)


def 获取状态(状态, 配置):
    cache = _加载(状态, 配置)
    return {"状态": cache.get("状态", "历史不足"), "明细": cache.get("明细", {})}


def 检查(哨兵价类型, K线数据, 状态, 配置):
    cache = _加载(状态, 配置)
    regime = cache.get("状态", "历史不足")
    if regime == "历史不足":
        passed = bool(配置.get("历史不足时放行", True))
        return {"通过": passed, "原因": "指数趋势历史不足", "状态": regime}
    passed = regime == "风险开启"
    return {
        "通过": passed,
        "原因": f"沪深300长期趋势{regime}",
        "状态": regime,
        "状态明细": cache.get("明细", {}),
    }
