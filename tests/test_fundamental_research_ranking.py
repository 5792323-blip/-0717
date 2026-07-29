import pandas as pd

from 基本面.生成个股研究排序 import 生成, 审计


def test_research_ranking_is_not_strict_admission():
    frame = pd.DataFrame([
        {"股票代码": "600519", "评分日期": "2026-07-28", "总分": 80, "置信度": .45,
         "评分状态": "可评价", "准入结论": "数据不足", "盈利质量覆盖率": 1},
        {"股票代码": "000001", "评分日期": "2026-07-28", "总分": 60, "置信度": .25,
         "评分状态": "数据不足", "准入结论": "数据不足", "盈利质量覆盖率": .5},
    ])
    result = 生成(frame)
    assert result.iloc[0]["研究状态"] == "可优先研究"
    assert result.iloc[0]["准入结论"] == "数据不足"
    audit = 审计(frame)
    assert audit["严格历史准入可用"] is False
