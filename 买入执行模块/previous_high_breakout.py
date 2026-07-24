"""上一根 K 线高点严格突破模块。"""

import math


def 前复权报价步长(前复权开盘, 不复权开盘, 不复权最小报价=0.01):
    """把真实报价步长折算到前复权价格坐标。"""
    try:
        adjusted_open = float(前复权开盘)
        raw_open = float(不复权开盘)
        raw_tick = float(不复权最小报价)
    except (TypeError, ValueError):
        return None
    if min(adjusted_open, raw_open, raw_tick) <= 0:
        return None
    return raw_tick / (raw_open / adjusted_open)


def 下一有效突破价(上一根最高价, 价格步长):
    """返回严格高于上一根最高价的最小可交易价。"""
    try:
        high, tick = float(上一根最高价), float(价格步长)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(high) or not math.isfinite(tick) or min(high, tick) <= 0:
        return None
    units = math.floor(high / tick + 1e-10)
    candidate = (units + 1) * tick
    while candidate <= high:
        candidate += tick
    return candidate

