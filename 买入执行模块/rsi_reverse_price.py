"""RSI 反推价独立模块。"""

import numpy as np

from 策略引擎.反推因子 import 反推RSI价位


def 计算(历史价格, 目标RSI, 周期=14):
    """按正式 SMA-RSI 口径反推下一价格点。

    ``历史价格`` 的最后一个点是上一根已完成 K 线的价格。RSI(14)
    需要 14 个变化，因此需要 14 个历史点产生 13 个已知变化，
    再把当前未知价格作为第 14 个变化参与求解。
    """
    window = list(历史价格 or [])
    if len(window) < 周期 + 1:
        return {"可用": False, "原因": f"反推历史不足{周期 + 1}个价格点"}
    try:
        window = np.asarray(window[-(周期 + 1):], dtype=float)
        target = float(目标RSI)
    except (TypeError, ValueError):
        return {"可用": False, "原因": "反推历史或目标无效"}
    if not np.isfinite(window).all() or not 0 < target < 100:
        return {"可用": False, "原因": "反推参数无效"}
    result = 反推RSI价位(window, 目标RSI=target, 周期=周期)
    value = result.get("目标价位")
    if value is None or not np.isfinite(float(value)) or float(value) <= 0:
        return {"可用": False, "原因": "反推价无效"}
    return {
        "可用": True,
        "RSI反推价": float(value),
        "目标RSI": target,
        "当前RSI": result.get("当前RSI"),
        "RSI算法": "SMA",
    }


def 计算SMA_RSI(历史价格, 周期=14):
    """返回与正式策略相同的 SMA RSI 最后一值。"""
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
    avg_gain = float(gains[-周期:].mean())
    avg_loss = float(losses[-周期:].mean())
    if avg_loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
