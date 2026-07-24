"""RSI 反推价独立模块。"""

import numpy as np

from 策略引擎.反推因子 import 反推RSI价位


def 计算(历史价格, 目标RSI):
    """只用传入的已完成历史价格计算目标 RSI 反推价。"""
    window = list(历史价格 or [])
    if len(window) < 15:
        return {"可用": False, "原因": "反推历史不足15根"}
    window = window[-15:]
    if any(value is None for value in window) or np.any(np.isnan(window)):
        return {"可用": False, "原因": "反推历史含缺失值"}
    result = 反推RSI价位(window, 目标RSI=float(目标RSI))
    value = result.get("目标价位")
    if value is None or not np.isfinite(float(value)) or float(value) <= 0:
        return {"可用": False, "原因": "反推价无效"}
    return {"可用": True, "RSI反推价": float(value), "目标RSI": float(目标RSI)}


def 计算Wilder上涨反推价(历史价格, 目标RSI, 周期=14):
    """按 TB/Wilder 状态，反推出下一根收盘价达到目标 RSI 的上涨价格。"""
    window = list(历史价格 or [])
    if len(window) < 周期 + 1:
        return {"可用": False, "原因": f"反推历史不足{周期 + 1}根"}
    try:
        values = np.asarray(window[-(周期 + 1):], dtype=float)
        target = float(目标RSI)
    except (TypeError, ValueError):
        return {"可用": False, "原因": "反推历史无效"}
    if not np.isfinite(values).all() or not 0 < target < 100:
        return {"可用": False, "原因": "反推参数无效"}
    changes = np.diff(values)
    if len(changes) < 周期:
        return {"可用": False, "原因": "反推历史不足一个完整 RSI 周期"}
    gains = np.maximum(changes, 0)
    losses = np.maximum(-changes, 0)
    # Match TradeBlazer/Wilder smoothing: initialize with the first
    # complete period, then recursively carry the state to the last close.
    avg_gain = float(gains[:周期].mean())
    avg_loss = float(losses[:周期].mean())
    for gain, loss in zip(gains[周期:], losses[周期:]):
        avg_gain = ((周期 - 1) * avg_gain + float(gain)) / 周期
        avg_loss = ((周期 - 1) * avg_loss + float(loss)) / 周期
    if avg_loss <= 0:
        return {"可用": False, "原因": "平均下跌幅为零"}
    target_rs = target / (100.0 - target)
    delta = (周期 - 1) * (target_rs * avg_loss - avg_gain)
    price = float(values[-1] + delta)
    if not np.isfinite(price) or price <= values[-1]:
        return {"可用": False, "原因": "目标 RSI 没有有效上涨解"}
    return {
        "可用": True,
        "RSI反推价": price,
        "目标RSI": target,
        "上一根收盘价": float(values[-1]),
        "平均上涨幅": avg_gain,
        "平均下跌幅": avg_loss,
        "当前RSI": 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss),
    }


def 计算WilderRSI(历史价格, 周期=14):
    """返回历史最后一根收盘后的 Wilder RSI，供目标档位选择使用。"""
    window = list(历史价格 or [])
    if len(window) < 周期 + 1:
        return None
    try:
        values = np.asarray(window, dtype=float)
    except (TypeError, ValueError):
        return None
    changes = np.diff(values)
    gains = np.maximum(changes, 0)
    losses = np.maximum(-changes, 0)
    if len(changes) < 周期:
        return None
    avg_gain = float(gains[:周期].mean())
    avg_loss = float(losses[:周期].mean())
    for gain, loss in zip(gains[周期:], losses[周期:]):
        avg_gain = ((周期 - 1) * avg_gain + float(gain)) / 周期
        avg_loss = ((周期 - 1) * avg_loss + float(loss)) / 周期
    if avg_loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
