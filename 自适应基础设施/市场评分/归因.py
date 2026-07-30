"""按Market Score状态统计组合收益和回撤。"""

from collections import defaultdict


def 状态归因(评分记录, 权益曲线):
    if not 评分记录 or not 权益曲线:
        return {}
    grouped = defaultdict(lambda: {"收益因子": 1.0, "权益序列": []})
    previous = None
    for score, point in zip(评分记录, 权益曲线):
        state = str(score.get("状态", "历史不足"))
        equity = float(point.get("权益", 0) or 0)
        grouped[state]["权益序列"].append(equity)
        if previous and previous > 0:
            grouped[state]["收益因子"] *= equity / previous
        previous = equity
    result = {}
    for state, group in grouped.items():
        values = group["权益序列"]
        start = values[0]
        end = values[-1]
        peak = start
        drawdown = 0.0
        for value in values:
            peak = max(peak, value)
            drawdown = max(drawdown, (peak - value) / max(peak, 1.0))
        result[state] = {
            "时间点": len(values),
            "起始权益": start,
            "结束权益": end,
            "区间收益率": grouped[state]["收益因子"] - 1,
            "最大回撤": drawdown,
        }
    return result
