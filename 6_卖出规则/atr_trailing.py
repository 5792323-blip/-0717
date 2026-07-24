# atr_trailing.py — ATR跟踪止盈止损
# 功能: 持仓期间最高价 - N*ATR 作为跟踪止盈/损线
#       价格上涨时线上移（锁定利润），不涨时不动
#       跌破即卖出
#
# MA方向调整: MA下降时ATR倍数放大(更宽松), MA上升时ATR倍数缩小(更紧密)
#   下降: 倍数 = 基础倍数 x (1 + |MA斜率|/调整因子)
#   上升: 倍数 = 基础倍数 x max(下限比例, 1 - MA斜率/调整因子)
#
# 用法:
#   配置: 卖出规则配置.yaml
#   atr_trailing:
#     启用: true
#     检查顺序: 2
#     ATR倍数: 2.5
#     MA调整倍率: 50
#     下限比例: 0.6

def 检查(持仓盈亏比例, 当前ATR, 买入价, 最高价=None, ATR倍数=2.5,
        MA斜率=None, MA调整倍率=50, 下限比例=0.6, **kwargs):
    if 买入价 is None or 买入价 == 0:
        return {"触发": False}

    if 当前ATR is None or 当前ATR <= 0:
        当前ATR = 买入价 * 0.02

    有效倍数 = ATR倍数
    if MA斜率 is not None and MA调整倍率 > 0:
        if MA斜率 < 0:
            调整 = 1 + abs(MA斜率) / MA调整倍率
            有效倍数 = ATR倍数 * 调整
        elif MA斜率 > 0:
            调整 = max(下限比例, 1 - MA斜率 / MA调整倍率)
            有效倍数 = ATR倍数 * 调整

    参考价 = 最高价 if (最高价 is not None and 最高价 > 0) else 买入价
    跟踪线 = 参考价 - 有效倍数 * 当前ATR

    ma_info = ""
    if MA斜率 is not None:
        ma_info = f" MA斜率{MA斜率:+.2f}->倍数{有效倍数:.1f}倍"

    return {
        "触发": True,
        "原因": f"ATR跟踪: 参考价{参考价:.2f} - {有效倍数:.1f}*ATR({当前ATR:.2f}) = {跟踪线:.2f}{ma_info}",
        "止损价": 跟踪线,
        "RSI峰值": None,
        "回落阈值": None,
        "ATR倍数": 有效倍数,
    }


if __name__ == "__main__":
    print("=" * 50)
    print("ATR跟踪止盈止损 - 自检测试(含MA调整)")
    print("=" * 50)
    for 买入, atr, 最高, 倍数, 斜率 in [
        (100, 3, None,    2.5, None),
        (100, 3, 115,     2.5,  1.5),
        (100, 3, 115,     2.5, -2.0),
        (100, 5, 120,     2.5,  3.0),
        (100, 3, 105,     3.0, -5.0),
        (100, 3, 110,     2.5,  0.5),
        (100, 3, 110,     2.5, -0.5),
    ]:
        结果 = 检查(0, atr, 买入, 最高价=最高, ATR倍数=倍数, MA斜率=斜率)
        线 = 结果["止损价"]
        print(f"  买入{买入:>3d} ATR{atr:.0f} 最高{str(最高 or ''):>4s} {倍数:.1f}倍 斜率{str(斜率 or '无'):>5s} -> 跟踪线{线:>7.2f}")

    print()
    print("OK ATR跟踪止盈止损 自检完成")
