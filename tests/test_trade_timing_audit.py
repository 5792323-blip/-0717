import pandas as pd

from 时序审计.trade_timing_audit import 审计回测


def test_strict_trade_audit_passes_inside_ohlc():
    trades = pd.DataFrame([{
        '类型': '买入', '前复权成交价': 101.0,
        '信号K线_最低': 99.0, '信号K线_最高': 102.0,
    }])
    result = 审计回测(trades, 'precomputed_stop_entry')
    assert result['结论'] == '通过'
    assert result['OHLC边界违规成交数'] == 0


def test_legacy_audit_is_never_formal_pass():
    result = 审计回测(pd.DataFrame(), 'intrabar_breakout')
    assert result['结论'] == '仅供对照'
    assert result['时序前视风险'] is True
