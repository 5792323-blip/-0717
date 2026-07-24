#!/usr/bin/env python3
"""RSI站岗价：RSI从高位回落后，用最高价减ATR缓冲形成保护线。"""


def 检查(
    持仓盈亏比例=None,
    当前ATR=None,
    买入价=None,
    最高价=None,
    RSI峰值=None,
    当前RSI=None,
    RSI下穿阈值=None,
    RSI下穿均线下限=50,
    ATR缓冲倍数=0.5,
    **kwargs,
):
    if None in (买入价, RSI峰值, 当前RSI) or 买入价 <= 0:
        return {"触发": False, "原因": "RSI站岗价缺少必要输入"}
    thresholds = sorted(RSI下穿阈值 or [80, 70], reverse=True)
    crossed = next((value for value in thresholds if RSI峰值 >= value > 当前RSI), None)
    if crossed is None or 当前RSI < float(RSI下穿均线下限):
        return {"触发": False, "原因": "RSI未满足高位下穿区间"}
    atr = float(当前ATR) if 当前ATR is not None and 当前ATR > 0 else float(买入价) * 0.02
    reference = max(float(最高价 or 买入价), float(买入价))
    guard = reference - float(ATR缓冲倍数) * atr
    return {
        "触发": True,
        "止损价": guard,
        "原因": f"RSI从峰值{RSI峰值:.1f}下穿{crossed}，站岗价{guard:.2f}",
        "RSI阈值": crossed,
    }


if __name__ == "__main__":
    assert 检查(当前ATR=2, 买入价=100, 最高价=115, RSI峰值=82, 当前RSI=75)["止损价"] == 114
    assert not 检查(当前ATR=2, 买入价=100, RSI峰值=75, 当前RSI=72)["触发"]
    print("RSI站岗价自检 OK")
