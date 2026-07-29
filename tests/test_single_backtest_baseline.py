import hashlib
import os

import pytest

from 回测引擎.backtest_engine import 跑回测


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "1_策略配置")
DATA = os.path.join(ROOT, "数据模块", "raw", "600519_双价格合并.pkl")


def _frame_digest(frame, columns):
    payload = frame[columns].fillna("").to_csv(
        index=False, float_format="%.10f"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@pytest.mark.skipif(not os.path.isfile(DATA), reason="缺少600519本地行情基线")
def test_verified_single_backtest_with_persistent_sentinel_is_stable():
    """锁定哨兵生命周期修复后的单股交易和逐K线状态。"""
    result = 跑回测(
        "600519",
        开始日期="2020-01-01",
        结束日期="2023-12-31",
        初始资金=20_000_000,
        配置目录=CONFIG,
        运行参数={"流动性上限比例": 0.01, "单股全仓模式": True},
        静默=True,
    )

    trades = result["交易明细"]
    process = result["持仓过程"]
    trade_columns = [
        "时间", "类型", "买入价", "卖出价", "成交数量", "交易费用",
        "信号类型", "卖出原因", "网格级别",
    ]
    process_columns = [
        "K线索引", "哨兵价", "本根触发哨兵价", "哨兵价跟踪启用",
        "哨兵价可执行", "哨兵价已消费价格", "最近成交哨兵价",
        "最终动作", "当前现金", "持仓市值", "权益", "持仓数量",
    ]

    assert result["买入次数"] == 173
    assert result["卖出次数"] == 172
    assert result["最终现金"] == pytest.approx(19_941_413.85478359, abs=1e-6)
    assert result["最终权益"] == pytest.approx(20_114_013.85478359, abs=1e-6)
    assert result["总收益率"] == pytest.approx(0.5700692739179545, abs=1e-9)
    assert _frame_digest(trades, trade_columns) == (
        "8f3346c74210309ee418e20ee4dbc43810777e1bc68e8edb89beb7b8ae49ca44"
    )
    assert _frame_digest(process, process_columns) == (
        "6d159f87c6d7ddbb008c2df1abdced164a755c1c494cb374a3b86f239205aa44"
    )
