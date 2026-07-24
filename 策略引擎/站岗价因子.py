# 站岗价因子.py — 持仓期间RSI回落对应的价格防线（独立因子程序）
#
# 对标买入哨兵价，完全对称：
#   买入：RSI上穿阈值 → 反推价 → 最高突破 → 哨兵价 → max(开盘,哨兵价)+滑点
#   卖出：RSI回落阈值 → 反推价 → 最低跌破+创新低 → 站岗价 → min(开盘,站岗价)-滑点
#
# 用法:
#   from 策略引擎.站岗价因子 import 计算站岗价
#   结果 = 计算站岗价(价格序列, 当前RSI, RSI峰值, 上根最低, 当前最低)
#   # 结果 = {站岗价, 反推价, 目标RSI, 是否触发, ...}

import numpy as np


def 计算站岗价(收盘价序列, 当前RSI=None, RSI峰值=None, 回落阈值=15,
               上根最低价=None, 当前最低价=None):
    """
    计算站岗价：持仓期间RSI回落阈值点对应的价格防线

    第1步: 目标RSI = RSI峰值 - 回落阈值
    第2步: 反推价 = RSI跌到目标RSI时对应的价格（用反推公式）
    第3步: 站岗价 = min(反推价, 上根最低价)
    触发条件: 当前最低 < 反推价 AND 当前最低 < 上根最低

    传入:
        收盘价序列  - list/array，至少15个前复权收盘价
                      (前14个已知 + 当前K线用上根收盘暂代)
        当前RSI    - 当前K线的RSI值
        RSI峰值    - 持仓期间RSI最高值
        回落阈值   - RSI从峰值回落的触发点（默认15）
        上根最低价  - 上根K线的前复权最低价
        当前最低价  - 当前K线的前复权最低价

    传出:
        字典: {站岗价, 反推价, 目标RSI, 是否触发, 触发说明, ...}
    """
    价格 = np.array(收盘价序列, dtype=float)
    if len(价格) < 15:
        return {"站岗价": None, "是否触发": False, "触发说明": "数据不足"}

    if 当前RSI is None or RSI峰值 is None:
        return {"站岗价": None, "是否触发": False, "触发说明": "RSI数据不足"}

    # ====== 第1步：目标RSI = 峰值 - 阈值 ======
    目标RSI = RSI峰值 - 回落阈值
    if 目标RSI <= 0:
        return {"站岗价": None, "是否触发": False,
                "目标RSI": 目标RSI, "触发说明": f"目标RSI({目标RSI:.1f})<=0，阈值过大"}

    # ====== 第2步：反推RSI跌到目标RSI时的价格 ======
    from 策略引擎.反推因子 import 反推RSI价位
    反推结果 = 反推RSI价位(收盘价序列, 目标RSI=目标RSI)
    反推价 = 反推结果.get('目标价位')

    if 反推价 is None:
        return {"站岗价": None, "是否触发": False,
                "目标RSI": round(目标RSI, 1), "触发说明": "反推价无效"}

    # ====== 第3步：判断两个触发条件 ======
    # 条件1: 当前最低价 < 反推价（价格跌破RSI回落目标对应的价位）
    触发条件1 = False
    if 当前最低价 is not None and 反推价 is not None:
        触发条件1 = 当前最低价 < 反推价

    # 条件2: 当前最低价 < 上根K线最低价（价格创出新低）
    触发条件2 = False
    if 当前最低价 is not None and 上根最低价 is not None:
        触发条件2 = 当前最低价 < 上根最低价

    # ====== 第4步：确定站岗价 ======
    # 站岗价 = min(反推价, 上根最低价)
    if 上根最低价 is not None:
        站岗价 = min(反推价, 上根最低价)
    else:
        站岗价 = 反推价

    # ====== 是否触发卖出 ======
    是否触发 = 触发条件1 and 触发条件2

    # ====== 构建说明 ======
    触发说明_parts = []
    if 触发条件1:
        触发说明_parts.append(f"最低{当前最低价:.2f}<反推{反推价:.2f}")
    else:
        if 当前最低价 is not None:
            触发说明_parts.append(f"最低{当前最低价:.2f}>=反推{反推价:.2f}")

    if 触发条件2:
        触发说明_parts.append(f"最低{当前最低价:.2f}<上根最低{上根最低价:.2f}")
    else:
        if 当前最低价 is not None and 上根最低价 is not None:
            触发说明_parts.append(f"最低{当前最低价:.2f}>=上根最低{上根最低价:.2f}")

    return {
        "站岗价": round(站岗价, 2),
        "反推价": round(反推价, 2),
        "目标RSI": round(目标RSI, 1),
        "当前RSI": round(当前RSI, 1),
        "RSI峰值": round(RSI峰值, 1),
        "涨跌方向": 反推结果.get('涨跌方向'),
        "是否触发": 是否触发,
        "触发条件1(跌破反推价)": 触发条件1,
        "触发条件2(创新低)": 触发条件2,
        "触发说明": " && ".join(触发说明_parts) if 触发说明_parts else "未满足条件",
    }


# ========== 自检 ==========
if __name__ == "__main__":
    print("=" * 50)
    print("站岗价因子 — 自检测试")
    print("=" * 50)

    import pandas as pd
    df = pd.read_pickle('数据模块/raw/600519_双价格合并.pkl')
    价格 = df['前复权_收盘'].values
    rsi = df['RSI_14'].values
    最低 = df['前复权_最低'].values

    # 找一根RSI≈70的K线作为"买入后RSI峰值"
    test_peaks = []
    for i in range(200, len(价格)):
        if 70 < rsi[i] < 72 and len(test_peaks) < 5:
            # 往后看几根，模拟RSI回落
            for j in range(i + 5, min(i + 15, len(价格) - 1)):
                if rsi[j] < rsi[i] - 14:
                    test_peaks.append((j, rsi[i], rsi[j]))
                    break

    for idx, 峰值, 当前 in test_peaks:
        窗口 = 价格[idx - 14:idx + 1]
        上根最低 = 最低[idx - 1] if idx > 0 else None
        当前低 = 最低[idx]

        结果 = 计算站岗价(
            收盘价序列=窗口,
            当前RSI=当前,
            RSI峰值=峰值,
            回落阈值=15,
            上根最低价=上根最低,
            当前最低价=当前低,
        )

        print(f"\n位置{idx}: RSI峰值{峰值:.1f}→当前{当前:.1f}")
        print(f"  反推价={结果['反推价']}, 目标RSI={结果['目标RSI']}")
        print(f"  上根最低={上根最低:.2f}, 当前最低={当前低:.2f}")
        print(f"  站岗价={结果['站岗价']}")
        print(f"  触发: {结果['是否触发']} ({结果['触发说明']})")

    print(f"\n✅ 站岗价因子自检完成")
