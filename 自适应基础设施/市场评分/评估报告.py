"""生成Market Score进入Active前的评估报告。"""

from 自适应基础设施.市场评分.诊断 import 诊断状态
from 自适应基础设施.市场评分.归因 import 状态归因


def 生成评估报告(评分记录, 权益曲线):
    stability = 诊断状态(评分记录)
    attribution = 状态归因(评分记录, 权益曲线)
    checks = {
        "评分有效率通过": stability["有效评分数"] == stability["记录数"] and stability["记录数"] > 0,
        "状态持续性通过": (
            stability["有效状态数"] > 0
            and stability["状态切换比例"] < 0.20
        ),
        "结果可归因": bool(attribution),
    }
    return {
        "结论": "建议进入只限制新增仓位的Active实验" if all(checks.values()) else "暂不建议进入Active",
        "验收项目": checks,
        "稳定性": stability,
        "状态归因": attribution,
    }
