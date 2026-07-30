"""生成Alpha Ranking进入独立实验前的评估报告。"""

from 自适应基础设施.Alpha排序.诊断 import 诊断排序


def 生成评估报告(records):
    diagnostics = 诊断排序(records)
    checks = {
        "覆盖率通过": diagnostics["有效覆盖率"] >= 0.80,
        "候选可生成": diagnostics["平均候选数"] > 0,
        "排序可诊断": diagnostics["评分平均值"] is not None,
    }
    return {
        "结论": "建议进入Alpha+RSI哨兵独立实验" if all(checks.values()) else "暂不建议进入独立实验",
        "验收项目": checks,
        "诊断": diagnostics,
    }
