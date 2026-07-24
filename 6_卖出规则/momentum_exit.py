# momentum_exit.py — RSI峰值回落动能衰竭退出
# 功能: RSI从持仓期间的最高点回落超过阈值 → 动能已尽 → 卖出
# 这能捕捉"RSI涨到69.9上不去，开始走弱"的经典场景

def 检查(持仓盈亏比例, 买入价, RSI峰值=None, 当前RSI=None, 回落阈值=None, **kwargs):
    """
    检查RSI是否从峰值回落 → 动能衰竭退出

    传入:
        持仓盈亏比例  - 当前盈亏比例
        RSI峰值       - 持仓期间RSI最高值
        当前RSI       - 当前RSI值
        回落阈值      - RSI从峰值回落到多少点触发（默认25）

    传出:
        字典: {"触发": True/False, "原因": "..."}
    """
    if 回落阈值 is None:
        回落阈值 = kwargs.get("基础回落阈值", 25)

    if RSI峰值 is None or 当前RSI is None:
        return {"触发": False}

    回落幅度 = RSI峰值 - 当前RSI

    if 回落幅度 >= 回落阈值:
        return {
            "触发": True,
            "原因": f"动能衰竭: RSI峰值{RSI峰值:.1f}回落{回落幅度:.1f}点(阈值{回落阈值})",
            "RSI峰值": RSI峰值,
            "回落阈值": 回落阈值,
        }

    return {"触发": False}


if __name__ == "__main__":
    print("=" * 40)
    print("动能衰竭退出 — 自检测试")
    print("=" * 40)
    测试集 = [
        (None, 45, False),
        (80, 50, True),
        (75, 62, False),
        (70, 54, False),
        (65, 60, False),
    ]
    for 峰值, 当前, 预期 in 测试集:
        结果 = 检查(0, 100, RSI峰值=峰值, 当前RSI=当前)
        实际 = 结果["触发"]
        print(f"  峰值{峰值} -> 当前{当前:>2} -> 回落{(峰值-当前) if 峰值 else '?'} -> {'触发' if 实际 else '不触发'} {'OK' if 实际 == 预期 else 'FAIL'}")

    print("OK momentum_exit 自检完成")
