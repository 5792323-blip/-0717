#!/usr/bin/env python3
"""使用上一交易日成交额确认入场流动性，避免读取当日未完成数据。"""

import math


def _数值(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def 检查(哨兵价类型, K线数据, 状态, 配置):
    适用信号 = 配置.get("适用信号", []) or []
    if 适用信号 and 哨兵价类型 not in 适用信号:
        return {
            "通过": True,
            "原因": f"{哨兵价类型}不在成交额过滤适用范围",
            "成交额比率": None,
        }

    最低比率 = float(配置.get("最低成交额比率", 0.7))
    比率 = _数值(K线数据.get("_上一交易日成交额比20日均值"))
    if 比率 is None:
        历史不足时放行 = bool(配置.get("历史不足时放行", True))
        return {
            "通过": 历史不足时放行,
            "原因": "上一交易日成交额历史不足，" + ("放行" if 历史不足时放行 else "拦截"),
            "成交额比率": None,
            "最低成交额比率": 最低比率,
        }

    通过 = 比率 >= 最低比率
    return {
        "通过": 通过,
        "原因": (
            f"上一交易日成交额比率{比率:.3f}"
            f"{'≥' if 通过 else '<'}{最低比率:.3f}，{'通过' if 通过 else '拦截'}"
        ),
        "成交额比率": 比率,
        "最低成交额比率": 最低比率,
    }
