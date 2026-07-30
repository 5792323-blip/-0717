"""Market Score Active与基线的实验归因。"""


def 生成Active归因(基线, shadow, active):
    baseline_live = 基线.get("live", {})
    shadow_live = shadow.get("live", {})
    active_live = active.get("live", {})
    baseline_curve = 基线.get("组合权益曲线", [])
    active_curve = active.get("组合权益曲线", [])
    return {
        "基线与Shadow结果一致": (
            baseline_live.get("实际成交") == shadow_live.get("实际成交")
            and baseline_live.get("当前权益") == shadow_live.get("当前权益")
            and baseline_curve == shadow.get("组合权益曲线", [])
        ),
        "基线": {
            "实际成交": baseline_live.get("实际成交"),
            "买入": baseline_live.get("实际买入"),
            "卖出": baseline_live.get("实际卖出"),
            "最终权益": baseline_live.get("当前权益"),
            "最大回撤": baseline_live.get("最大回撤"),
        },
        "Shadow": {
            "实际成交": shadow_live.get("实际成交"),
            "最终权益": shadow_live.get("当前权益"),
            "未解释审批差异": shadow_live.get("Shadow未解释差异"),
        },
        "Active": {
            "实际成交": active_live.get("实际成交"),
            "买入": active_live.get("实际买入"),
            "卖出": active_live.get("实际卖出"),
            "最终权益": active_live.get("当前权益"),
            "最大回撤": active_live.get("最大回撤"),
            "市场状态分布": active_live.get("市场状态分布", {}),
        },
        "Active相对基线": {
            "成交变化": active_live.get("实际成交", 0) - baseline_live.get("实际成交", 0),
            "买入变化": active_live.get("实际买入", 0) - baseline_live.get("实际买入", 0),
            "最终权益变化": active_live.get("当前权益", 0) - baseline_live.get("当前权益", 0),
            "最终权益变化比例": (
                active_live.get("当前权益", 0) / baseline_live.get("当前权益", 1) - 1
            ),
            "最大回撤变化": active_live.get("最大回撤", 0) - baseline_live.get("最大回撤", 0),
        },
        "权益曲线长度一致": len(baseline_curve) == len(active_curve),
    }

