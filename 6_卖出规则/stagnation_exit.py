#!/usr/bin/env python3
"""无效交易退出：持仓早期没有产生最低浮盈且仍亏损时离场。"""


def 检查(
    持仓盈亏比例,
    持有K线数=None,
    最高价=None,
    前复权买入价=None,
    检查K线数=4,
    最低MFE=0.005,
    **kwargs,
):
    if (
        持仓盈亏比例 is None
        or 持有K线数 is None
        or 最高价 is None
        or 前复权买入价 is None
        or 前复权买入价 <= 0
    ):
        return {"触发": False}

    mfe = 最高价 / 前复权买入价 - 1
    # 浮点计算中0.5%可能表示为0.004999999，阈值相等应视为已达到。
    未达到最低浮盈 = mfe + 1e-12 < float(最低MFE)
    if 持有K线数 >= int(检查K线数) and 未达到最低浮盈 and 持仓盈亏比例 < 0:
        return {
            "触发": True,
            "原因": (
                f"无效交易退出: 持有{持有K线数}根，"
                f"最大浮盈{mfe:.2%}<{float(最低MFE):.2%}且当前亏损"
            ),
            "MFE": mfe,
        }
    return {"触发": False, "MFE": mfe}
