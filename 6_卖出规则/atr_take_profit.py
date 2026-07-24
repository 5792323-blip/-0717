# atr_take_profit.py — ATR跟踪止盈（仅盈利触发）
#
# 与 atr_trailing.py 有意分开：该因子只有在持仓净盈亏达到启动盈利比例后，
# 才会生成 ATR 跟踪线；浮亏或未盈利时始终不触发。这样可以单独测试
# “锁定已经获得的利润”，而不会把它误当成 ATR 止损。

def 检查(持仓盈亏比例, 当前ATR, 买入价, 最高价=None, ATR倍数=2.5,
        启动盈利比例=0.0, MA斜率=None, MA调整倍率=50, 下限比例=0.6,
        **kwargs):
    """返回 ATR 止盈检查结果。

    持仓盈亏比例由执行器按净收入计算，启动盈利比例默认 0，采用严格的
    ``>`` 判断，因此刚好保本不会触发。触发后的价格跌破判断仍由执行器
    使用当根最低价完成，避免本模块引入未来数据。
    """
    try:
        盈亏 = float(持仓盈亏比例)
    except (TypeError, ValueError):
        盈亏 = 0.0
    try:
        启动线 = float(启动盈利比例)
    except (TypeError, ValueError):
        启动线 = 0.0

    if 盈亏 <= 启动线:
        return {
            "触发": False,
            "原因": f"ATR跟踪止盈未启动：当前净盈亏{盈亏:.2%}，需>{启动线:.2%}",
        }
    if 买入价 is None or 买入价 == 0:
        return {"触发": False, "原因": "缺少有效买入价"}

    if 当前ATR is None or 当前ATR <= 0:
        当前ATR = 买入价 * 0.02

    有效倍数 = float(ATR倍数)
    if MA斜率 is not None and MA调整倍率 > 0:
        if MA斜率 < 0:
            有效倍数 *= 1 + abs(MA斜率) / MA调整倍率
        elif MA斜率 > 0:
            有效倍数 *= max(下限比例, 1 - MA斜率 / MA调整倍率)

    参考价 = 最高价 if (最高价 is not None and 最高价 > 0) else 买入价
    跟踪线 = 参考价 - 有效倍数 * 当前ATR
    ma_info = ""
    if MA斜率 is not None:
        ma_info = f" MA斜率{MA斜率:+.2f}->倍数{有效倍数:.1f}倍"
    return {
        "触发": True,
        "原因": (f"ATR跟踪止盈：净盈亏{盈亏:.2%}，参考价{参考价:.2f} - "
                 f"{有效倍数:.1f}*ATR({当前ATR:.2f}) = {跟踪线:.2f}{ma_info}"),
        "止损价": 跟踪线,
        "RSI峰值": None,
        "回落阈值": None,
        "ATR倍数": 有效倍数,
    }


if __name__ == "__main__":
    assert not 检查(-0.01, 3, 100, 110)["触发"]
    assert not 检查(0.0, 3, 100, 110)["触发"]
    assert 检查(0.01, 3, 100, 110)["触发"]
    print("OK ATR跟踪止盈（仅盈利触发）自检完成")
