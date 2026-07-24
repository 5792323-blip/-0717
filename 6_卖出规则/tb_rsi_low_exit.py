# tb_rsi_low_exit.py — TB最低价RSI下穿卖出
# 功能: 复刻交易开拓者思路中“卖出使用最低价RSI下穿”的对照规则。


def 检查(
    持仓盈亏比例=None,
    上一根最低价RSI=None,
    当前最低价RSI=None,
    下穿阈值=None,
    **kwargs,
):
    """
    检查最低价 RSI 是否从上方向下穿越指定阈值。

    传入:
        上一根最低价RSI - 上一根K线最低价计算的 RSI
        当前最低价RSI   - 当前K线最低价计算的 RSI
        下穿阈值         - 可为单个数值或列表，默认 [70, 30, 20]

    传出:
        字典: {"触发": True/False, "卖出比例": 1.0, "原因": "..."}
    """
    if 上一根最低价RSI is None or 当前最低价RSI is None:
        return {"触发": False, "原因": "缺少最低价RSI"}

    thresholds = 下穿阈值 if isinstance(下穿阈值, list) else (下穿阈值 or [70, 30, 20])
    thresholds = sorted([float(x) for x in thresholds], reverse=True)
    prev_value = float(上一根最低价RSI)
    current_value = float(当前最低价RSI)

    crossed = next((value for value in thresholds if prev_value >= value > current_value), None)
    if crossed is None:
        return {"触发": False, "原因": "最低价RSI未下穿阈值"}

    return {
        "触发": True,
        "卖出比例": 1.0,
        "原因": f"TB最低价RSI下穿{crossed:g}: {prev_value:.1f} → {current_value:.1f}",
        "RSI阈值": crossed,
    }
