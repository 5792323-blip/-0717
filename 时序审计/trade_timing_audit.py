"""每次回测的买入时序与 OHLC 成交边界审计。"""

import pandas as pd

from 买入执行模块.entry_timing import LEGACY_SAME_BAR, TB_REPLAY, 规范化模式


def 审计回测(交易明细, 买入时机模式):
    mode = 规范化模式(买入时机模式)
    trades = 交易明细 if isinstance(交易明细, pd.DataFrame) else pd.DataFrame()
    buys = trades[trades.get('类型', pd.Series(index=trades.index, dtype=object)) == '买入'].copy()
    violations = 0
    required = {'前复权成交价', '信号K线_最高', '信号K线_最低'}
    if len(buys) and required.issubset(buys.columns):
        fill = pd.to_numeric(buys['前复权成交价'], errors='coerce')
        high = pd.to_numeric(buys['信号K线_最高'], errors='coerce')
        low = pd.to_numeric(buys['信号K线_最低'], errors='coerce')
        violations = int(((fill > high + high.abs() * 1e-10) | (fill < low - low.abs() * 1e-10)).fillna(False).sum())
    legacy = mode in (LEGACY_SAME_BAR, TB_REPLAY)
    passed = not legacy and violations == 0
    return {
        '结论': '通过' if passed else ('仅供对照' if legacy and violations == 0 else '未通过'),
        '标准化买入时机': mode,
        '时序前视风险': bool(legacy),
        'OHLC边界违规成交数': violations,
        '买入样本数': int(len(buys)),
        '说明': (
            '旧版模式会用当根收盘RSI倒推当根盘中成交，不得用于正式结论。'
            if legacy else '买入订单与成交价格已按可用数据时点和OHLC边界审计。'
        ),
    }
