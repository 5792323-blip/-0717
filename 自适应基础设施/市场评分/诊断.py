"""Market Score Shadow状态稳定性诊断。"""

from collections import Counter


def 诊断状态(records):
    states = [str(row.get("状态", "历史不足")) for row in records]
    valid_states = [state for state in states if state != "历史不足"]
    scores = [row.get("市场评分") for row in records if row.get("市场评分") is not None]
    transitions = sum(1 for before, after in zip(valid_states, valid_states[1:]) if before != after)
    runs = []
    if valid_states:
        start = valid_states[0]
        length = 1
        for state in valid_states[1:]:
            if state == start:
                length += 1
            else:
                runs.append((start, length))
                start, length = state, 1
        runs.append((start, length))
    return {
        "记录数": len(states),
        "有效状态数": len(valid_states),
        "有效评分数": len(scores),
        "状态分布": dict(Counter(states)),
        "状态切换次数": transitions,
        "状态切换比例": transitions / max(len(valid_states) - 1, 1),
        "最短状态持续点数": min((length for _, length in runs), default=0),
        "平均状态持续点数": sum(length for _, length in runs) / max(len(runs), 1),
        "评分最小值": min(scores) if scores else None,
        "评分最大值": max(scores) if scores else None,
        "评分平均值": sum(scores) / len(scores) if scores else None,
    }
