from 研究实验 import robust_signal_walkforward as module


def make_report(year_return, drawdown=0.01, ratio=1.2, trades=100):
    details = []
    for index in range(6):
        details.append({
            "股票代码": f"00000{index}",
            "卖出次数": trades // 6,
            "胜率": 0.4,
            "年化收益率": year_return,
            "最大回撤": drawdown,
            "盈亏比": ratio,
        })
    return {
        "汇总": {
            "股票数": 6,
            "总交易数": trades,
            "平均年化收益率": year_return,
            "平均最大回撤": drawdown,
            "加权胜率": 0.4,
            "平均盈亏比": ratio,
        },
        "股票明细": details,
    }


def test_generates_all_nonempty_signal_combinations():
    plans = module.生成信号方案()
    assert len(plans) == 15
    assert plans["20+30+MA+70"] == [
        "rsi_cross_20", "rsi_cross_30", "rsi_cross_ma", "rsi_cross_70"
    ]


def test_positive_years_and_cells_pass_hard_constraints():
    reports = {year: make_report(0.01) for year in module.年度}
    buckets = {f"00000{index}": index % 3 for index in range(6)}
    result = module.评价方案(reports, buckets, bucket_count=3, minimum_positive_cells=9)
    assert result["合格"] is True
    assert result["正收益年度数"] == 4
    assert result["正收益横截面单元数"] == 12


def test_one_negative_year_fails_even_when_average_is_positive():
    reports = {year: make_report(0.01) for year in module.年度}
    reports[2022] = make_report(-0.001)
    buckets = {f"00000{index}": index % 3 for index in range(6)}
    result = module.评价方案(reports, buckets, bucket_count=3, minimum_positive_cells=9)
    assert result["平均年度收益"] > 0
    assert result["合格"] is False
    assert result["硬约束"]["所有年度收益为正"] is False
