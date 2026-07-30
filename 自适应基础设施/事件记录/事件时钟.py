"""当前事件顺序与目标集中顺序的旁路比较。"""


def 事件类型(row):
    kind = str(row.get("类型", ""))
    return "卖出" if kind == "卖出" else "买入" if kind == "买入" else "其他"


def 比较事件顺序(records):
    actual = [事件类型(row) for row in records if 事件类型(row) != "其他"]
    target = sorted(enumerate(actual), key=lambda item: (item[1] != "卖出", item[0]))
    positions = [position for position, _ in target]
    return {
        "实际事件顺序": actual,
        "目标事件顺序": [actual[position] for position in positions],
        "是否需要调整": positions != list(range(len(actual))),
        "事件数量": len(actual),
    }
