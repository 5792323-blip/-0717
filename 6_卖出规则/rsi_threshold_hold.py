"""RSI 阈值守仓：在 RSI 未跌回最近上穿关卡前，暂缓指定卖出规则。"""


关卡顺序 = ((80, "RSI上穿80"), (70, "RSI上穿70"), (30, "RSI上穿30"), (20, "RSI上穿20"))


def 更新(状态, 上一RSI, 当前RSI, 当前RSI均线):
    """用已经完成的 RSI 数据更新守仓状态，返回新的状态字典。

    RSI 一根 K 线可能跨越多个固定阈值，取其中最高关卡；RSI 均线
    关卡在未触及更高固定阈值时生效。下穿最近锁定关卡后解除保护。
    """
    result = dict(状态 or {})
    try:
        previous = float(上一RSI)
        current = float(当前RSI)
    except (TypeError, ValueError):
        return result

    crossed = next(((value, name) for value, name in 关卡顺序 if previous < value <= current), None)
    if crossed is None:
        try:
            average = float(当前RSI均线)
        except (TypeError, ValueError):
            average = None
        if average is not None and previous < average <= current:
            crossed = (average, "RSI上穿均线")

    if crossed is not None:
        result.update({"守仓中": True, "阈值": crossed[0], "阈值名称": crossed[1]})
    elif result.get("守仓中") and current < float(result.get("阈值", current)):
        result.update({"守仓中": False, "解除原因": f"RSI下穿{result.get('阈值名称', '守仓阈值')}"})

    result["当前RSI"] = current
    return result


def 应暂缓(状态, 规则英文标识, 暂缓卖出规则):
    """仅在守仓生效且规则被配置为暂缓时返回 True。"""
    return bool((状态 or {}).get("守仓中") and 规则英文标识 in (暂缓卖出规则 or []))


def 检查(**_kwargs):
    """模块审计兼容接口：守仓由执行器作为保护层调用，绝不直接触发卖出。"""
    return {"触发": False, "原因": "RSI阈值守仓为ATR保护层，不直接卖出"}
