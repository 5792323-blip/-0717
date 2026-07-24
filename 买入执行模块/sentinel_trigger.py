"""RSI 反推价与上一根高点的组合触发模块。"""

import math

from 买入执行模块.previous_high_breakout import (
    下一有效突破价, 前复权报价步长,
)


def _向上取整(价格, 步长):
    return math.ceil(float(价格) / float(步长) - 1e-10) * float(步长)


def 形成候选(RSI反推价, 上一根最高价):
    """在已完成 K 线收盘后保存下一根所需的两条独立边界。"""
    reverse, previous_high = float(RSI反推价), float(上一根最高价)
    return {
        "RSI反推价": reverse,
        "上一根最高价": previous_high,
        # 仅用于画线；实际触发价要按本根复权比例换算报价步长。
        "触发边界": max(reverse, previous_high),
    }


def 评估触发(RSI反推价, 上一根最高价, K线数据, 不复权最小报价=0.01):
    """
    必须满足：本根最高价达到哨兵价。
    哨兵价 = max(RSI反推价, 上一根最高价)。不再额外叠加一个最小报价单位，
    买入溢价只在后续成交价格计算中使用。
    不读取本根收盘价、本根 RSI 或本根 RSI 均线。
    """
    tick = 前复权报价步长(
        K线数据.get('前复权_开盘'), K线数据.get('不复权_开盘'), 不复权最小报价,
    )
    try:
        reverse = float(RSI反推价)
        previous_high = float(上一根最高价)
        current_high = float(K线数据.get('前复权_最高'))
    except (TypeError, ValueError):
        return {"满足": False, "原因": "严格触发价格缺失"}
    if min(reverse, previous_high, current_high) <= 0:
        return {"满足": False, "原因": "严格触发价格无效"}
    # 哨兵价是条件单触发边界，触达即可触发；不再额外抬高一个报价单位。
    reverse_trigger = _向上取整(reverse, tick) if tick else reverse
    high_trigger = previous_high
    final_trigger = max(reverse_trigger, high_trigger)
    reverse_ok = current_high >= reverse_trigger
    high_ok = current_high >= high_trigger
    limiting = "RSI反推价" if reverse >= previous_high else "上一根高点突破"
    return {
        "满足": bool(reverse_ok and high_ok),
        "RSI反推价": reverse,
        "RSI反推触发价": reverse_trigger,
        "上一根最高价": previous_high,
        "前高突破价": high_trigger,
        "最终买入触发价": final_trigger,
        "本根最高价": current_high,
        "RSI价格条件": reverse_ok,
        "前高突破条件": high_ok,
        "限制条件": limiting,
        "价格步长": tick,
        "原因": "两项价格条件均通过" if reverse_ok and high_ok else (
            "本根未达到RSI反推价" if not reverse_ok else "本根未达到上一根最高价"
        ),
    }
