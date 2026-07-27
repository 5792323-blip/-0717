from 因子模块.position_sizing import 凯利仓位管理


def _params():
    return {
        "凯利折扣": 0.5,
        "最小样本数": 30,
        "单股上限比例": 0.10,
        "总仓位上限比例": 0.98,
        "现金底线比例": 0.20,
        "高波动阈值": 0.40,
        "高波动折扣": 0.70,
        "低波动阈值": 0.20,
        "低波动加成": 1.00,
        "信号统计": {
            "RSI上穿70": {"胜率": 0.60, "平均盈利": 0.10, "平均亏损": 0.05, "样本数": 100},
        },
    }


def test_half_kelly_is_scaled_by_volatility_and_capped():
    factor = 凯利仓位管理(_params())
    result = factor.买入前检查(
        {"信号类型": "RSI上穿70", "前复权_收盘": 100, "ATR_14": 5},
        {"信号类型": "RSI上穿70", "总权益": 1_000_000, "当前持仓市值": 0, "当前现金": 1_000_000},
    )
    assert result["允许买入"] is True
    assert result["波动率调整"] == 0.7
    assert result["建议仓位"] <= 100_000


def test_each_rsi_signal_uses_its_own_statistics():
    factor = 凯利仓位管理(_params())
    result = factor.买入前检查(
        {"信号类型": "RSI上穿30", "前复权_收盘": 100, "ATR_14": 1},
        {"信号类型": "RSI上穿30", "总权益": 1_000_000, "当前现金": 1_000_000},
    )
    assert result["允许买入"] is False
    assert "未配置" in result["说明"] or "统计不足" in result["说明"]


def test_kelly_respects_cash_floor_and_total_position_cap():
    factor = 凯利仓位管理(_params())
    result = factor.买入前检查(
        {"信号类型": "RSI上穿70", "前复权_收盘": 100, "ATR_14": 1},
        {"信号类型": "RSI上穿70", "总权益": 1_000_000,
         "当前持仓市值": 980_000, "当前现金": 20_000},
    )
    assert result["允许买入"] is False
