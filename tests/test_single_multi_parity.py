import hashlib
import os

import pytest

from 回测引擎.backtest_engine import 跑回测
from 组合回测.统一多股执行器 import 运行共享账户回测


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "1_策略配置")
DATA = os.path.join(ROOT, "数据模块", "raw", "600519_双价格合并.pkl")


def _digest(frame, columns):
    return hashlib.sha256(
        frame[columns].fillna("").to_csv(
            index=False, float_format="%.10f"
        ).encode("utf-8")
    ).hexdigest()


@pytest.mark.skipif(not os.path.isfile(DATA), reason="缺少600519本地行情")
def test_one_stock_shared_mode_matches_single_engine_exactly():
    runtime = {"流动性上限比例": 0.01, "多股资金池模式": True}
    single = 跑回测(
        "600519", "2020-01-01", "2023-12-31", 20_000_000,
        配置目录=CONFIG, 运行参数=runtime, 静默=True,
    )
    shared = 运行共享账户回测(
        ["600519"], "2020-01-01", "2023-12-31", 20_000_000,
        CONFIG, liquidity_limit=0.01,
    )["股票结果"][0]

    trade_columns = [
        "时间", "类型", "买入价", "卖出价", "成交数量", "交易费用",
        "信号类型", "卖出原因", "网格级别",
    ]
    process_columns = [
        "K线索引", "哨兵价", "本根触发哨兵价", "哨兵价跟踪启用",
        "哨兵价可执行", "哨兵价已消费价格", "最近成交哨兵价",
        "最终动作", "当前现金", "持仓市值", "权益", "持仓数量",
    ]
    assert _digest(shared["交易明细"], trade_columns) == _digest(
        single["交易明细"], trade_columns
    )
    assert _digest(shared["持仓过程"], process_columns) == _digest(
        single["持仓过程"], process_columns
    )
    assert shared["最终现金"] == pytest.approx(single["最终现金"], abs=1e-6)
    assert shared["最终权益"] == pytest.approx(single["最终权益"], abs=1e-6)
