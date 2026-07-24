#!/usr/bin/env python3
"""背离修正：顶背离可独立加速退出，底背离只给出暂缓建议。"""


def 检查(
    有底背离=False,
    有顶背离=False,
    持有K线数=None,
    底背离暂缓K线数=3,
    顶背离加速=True,
    **kwargs,
):
    if 有顶背离 and 顶背离加速:
        return {"触发": True, "原因": "出现RSI顶背离，加速退出", "修正": "加速"}
    if 有底背离:
        return {
            "触发": False,
            "原因": f"出现RSI底背离，建议暂缓{int(底背离暂缓K线数)}根K线",
            "修正": "暂缓",
            "暂缓K线数": int(底背离暂缓K线数),
        }
    return {"触发": False, "原因": "无背离修正"}


if __name__ == "__main__":
    assert 检查(有顶背离=True)["触发"]
    assert 检查(有底背离=True)["修正"] == "暂缓"
    print("背离修正自检 OK")
