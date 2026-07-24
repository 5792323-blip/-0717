#!/usr/bin/env python3
"""由训练期锁定模型驱动的复合Alpha买入过滤。"""

import json
import os

import numpy as np
import pandas as pd


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _模型路径(配置):
    path = 配置.get("模型文件", "1_策略配置/扩展因子模型.json")
    return path if os.path.isabs(path) else os.path.join(项目根目录, path)


def _加载模型(状态, 配置):
    cache = 状态.setdefault("alpha_composite_filter", {})
    if "模型" not in cache:
        with open(_模型路径(配置), encoding="utf-8") as source:
            cache["模型"] = json.load(source)
        cache["日线历史"] = []
        cache["当前日"] = None
        cache["当日K线"] = None
        cache["得分"] = None
        cache["因子值"] = {}
    return cache


def _完成日线(cache):
    daily = cache.get("当日K线")
    if not daily:
        return
    cache["日线历史"].append(daily)
    cache["日线历史"] = cache["日线历史"][-80:]
    frame = pd.DataFrame(cache["日线历史"]).set_index("date")
    from 回测引擎.factor_mining import 计算候选因子
    latest = 计算候选因子(frame).iloc[-1]
    score = 0.0
    values = {}
    for factor in cache["模型"]["因子"]:
        name = factor["名称"]
        value = latest.get(name)
        if value is None or not np.isfinite(value):
            cache["得分"] = None
            cache["因子值"] = {}
            return
        z_score = (float(value) - factor["训练均值"]) / factor["训练标准差"]
        contribution = factor["权重"] * factor["方向"] * z_score
        values[name] = {"原值": float(value), "标准分": z_score, "贡献": contribution}
        score += contribution
    cache["得分"] = float(score)
    cache["因子值"] = values


def 更新(K线数据, 状态, 配置):
    cache = _加载模型(状态, 配置)
    date = str(K线数据.get("日期", ""))[:10]
    if not date:
        return
    if cache["当前日"] != date:
        _完成日线(cache)
        cache["当前日"] = date
        cache["当日K线"] = None
    bar = {
        "date": pd.Timestamp(date),
        "open": float(K线数据.get("前复权_开盘", np.nan)),
        "high": float(K线数据.get("前复权_最高", np.nan)),
        "low": float(K线数据.get("前复权_最低", np.nan)),
        "close": float(K线数据.get("前复权_收盘", np.nan)),
        "volume": float(K线数据.get("成交量", 0) or 0),
        "rsi": float(K线数据.get("RSI_14", np.nan)),
        "atr": float(K线数据.get("ATR_14", np.nan)),
    }
    if cache["当日K线"] is None:
        cache["当日K线"] = bar
    else:
        daily = cache["当日K线"]
        daily["high"] = max(daily["high"], bar["high"])
        daily["low"] = min(daily["low"], bar["low"])
        daily["close"] = bar["close"]
        daily["volume"] += bar["volume"]
        daily["rsi"] = bar["rsi"]
        daily["atr"] = bar["atr"]


def 获取状态(状态, 配置):
    cache = _加载模型(状态, 配置)
    return {
        "得分": cache.get("得分"),
        "因子值": cache.get("因子值", {}),
        "模型版本": cache.get("模型", {}).get("模型版本"),
    }


def 检查(哨兵价类型, K线数据, 状态, 配置):
    cache = _加载模型(状态, 配置)
    score = cache.get("得分")
    if score is None:
        return {"通过": bool(配置.get("历史不足时放行", True)), "原因": "扩展因子历史不足"}
    threshold = float(配置.get("得分阈值", cache["模型"].get("得分阈值", 0.0)))
    passed = score > threshold
    return {
        "通过": passed,
        "原因": f"前一交易日扩展因子得分{score:.3f}{'>' if passed else '<='}{threshold:.3f}",
        "得分": score,
        "阈值": threshold,
        "因子值": cache.get("因子值", {}),
    }
