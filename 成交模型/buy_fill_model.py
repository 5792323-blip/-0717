"""不超出 OHLC 可观察范围的买入成交模型。"""

import math


def 计算买入成交(开盘, 最高, 最低, 触发价, 买入溢价=1.0, 按开盘成交=False):
    """
    返回 ``{可成交, 基准价, 成交价, 原因}``。

    跳空高开按开盘作为基准；盘中触发按触发价作为基准。
    买入溢价是成交价上限，不是必须额外支付的价格；若计划价超出当根
    最高价，则按当根最高价成交并保留截断信息。
    """
    try:
        open_price, high_price, low_price = map(float, (开盘, 最高, 最低))
        trigger = float(触发价 if 触发价 is not None else open_price)
        premium = float(买入溢价)
    except (TypeError, ValueError):
        return {"可成交": False, "原因": "成交价格非法"}
    values = (open_price, high_price, low_price, trigger, premium)
    if not all(math.isfinite(x) for x in values) or min(open_price, high_price, low_price, trigger, premium) <= 0:
        return {"可成交": False, "原因": "成交价格非法"}
    if low_price > high_price or not low_price <= open_price <= high_price:
        return {"可成交": False, "原因": "K线OHLC范围非法"}
    if not 按开盘成交 and high_price < trigger:
        return {"可成交": False, "原因": "最高价未触发哨兵价"}
    base = open_price if 按开盘成交 else max(open_price, trigger)
    fill = base * premium
    计划成交价 = fill
    fill = min(fill, high_price)
    if fill < low_price:
        return {"可成交": False, "基准价": base, "计划成交价": fill, "原因": "成交价低于当根最低价"}
    return {
        "可成交": True, "基准价": base, "计划成交价": 计划成交价,
        "成交价": fill,
        "价格已按最高价截断": fill < 计划成交价,
        "原因": "严格OHLC成交（买入溢价为上限）",
    }


def 计算回撤买入成交(开盘, 最高, 最低, 触发价, 买入溢价=1.0):
    """
    回撤触发买入成交模型（适用于网格加仓）：

    - 触发条件：当根最低价 <= 触发价（表示价格回撤触达）
    - 若跳空低开（开盘 < 触发价），则按开盘作为基准（无法以更高触发价成交）
    - 否则按触发价作为基准（触达即买）
    - 买入溢价是成交价上限，超过当根最高价时按最高价成交
    """
    try:
        open_price, high_price, low_price = map(float, (开盘, 最高, 最低))
        trigger = float(触发价 if 触发价 is not None else open_price)
        premium = float(买入溢价)
    except (TypeError, ValueError):
        return {"可成交": False, "原因": "成交价格非法"}
    values = (open_price, high_price, low_price, trigger, premium)
    if not all(math.isfinite(x) for x in values) or min(open_price, high_price, low_price, trigger, premium) <= 0:
        return {"可成交": False, "原因": "成交价格非法"}
    if low_price > high_price or not low_price <= open_price <= high_price:
        return {"可成交": False, "原因": "K线OHLC范围非法"}
    if low_price > trigger:
        return {"可成交": False, "原因": "最低价未触达回撤触发价"}

    base = open_price if open_price < trigger else trigger
    fill = base * premium
    计划成交价 = fill
    fill = min(fill, high_price)
    if fill < low_price:
        return {"可成交": False, "基准价": base, "计划成交价": fill, "原因": "成交价低于当根最低价"}
    return {
        "可成交": True, "基准价": base, "计划成交价": 计划成交价,
        "成交价": fill,
        "价格已按最高价截断": fill < 计划成交价,
        "原因": "回撤触发严格OHLC成交（买入溢价为上限）",
    }
