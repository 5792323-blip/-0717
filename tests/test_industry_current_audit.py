import pandas as pd

from 基本面.审计行业景气当前台账 import 审计


def test_current_workbook_without_publish_dates_is_not_ready(tmp_path):
    path = tmp_path / "v3.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({
            "指标键": ["A"], "行业": ["食品饮料"], "当前值（原始）": [1],
            "当前评分(1-10)": [7], "数据发布日期": [None], "数据状态": ["待更新"],
            "建议权重": [1], "角色": ["核心先行"],
        }).to_excel(writer, sheet_name="指标更新台账_v3", index=False)
    result = 审计(path)
    assert not result["通过"]
    assert result["有发布日期数"] == 0
