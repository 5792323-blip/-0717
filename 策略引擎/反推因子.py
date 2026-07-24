# 反推因子.py — 从目标RSI反推收盘价
# 功能: 给定目标RSI值或当前状态，反算出下一根K线需要多少收盘价
# 用途: 设定哨兵价、止盈止损位、买入触发价
#
# 原理: RSI = 100 - 100/(1+RS)
#       RS = avg_gain / avg_loss
#       知道前13根涨跌 + 目标RSI → 解出第14根收盘价
#
# 更新: RSI_MA用上一根固定值（不参与当前K线计算）
#       目标RSI根据当前RSI位置自动选择：
#         RSI < 20         → 反推RSI=20  (上穿20)
#         20 ≤ RSI < MA_prev → 反推RSI=MA_prev  (上穿均线)
#         MA_prev ≤ RSI < 30 → 反推RSI=30  (上穿30)
#         30 ≤ RSI < 70    → 反推RSI=70  (上穿70)
#         RSI ≥ 70         → 无买入信号
#
# 用法:
#   from 策略引擎.反推因子 import 反推RSI价位, 智能反推
#   价位 = 反推RSI价位(最近15根前复权收盘价, 目标RSI=20)
#   结果 = 智能反推(最近15根前复权收盘价, RSI_MA_上一根=25.14)

import numpy as np


def 反推RSI价位(收盘价序列, 目标RSI=20, 周期=14):
    """
    从目标RSI反推收盘价（核心算法）

    传入:
        收盘价序列  - list或array，至少(周期+1)=15个前复权收盘价
                     最后一个是当前K线收盘价
        目标RSI    - 希望下一根K线达到的RSI值
        周期       - RSI计算周期，默认14

    传出:
        字典 {目标价位, 涨跌方向, 涨跌幅度, 当前RSI, ...}
    """
    价格 = np.array(收盘价序列, dtype=float)
    if len(价格) < 周期 + 1:
        return {"目标价位": None, "涨跌方向": "数据不足",
                "说明": f"至少需要{周期+1}个价格，传入{len(价格)}个"}

    窗口价格 = 价格[-(周期 + 1):]
    当前收盘 = 窗口价格[-1]

    # 前14个价格 = 窗口价格[1:] → 13个diff（当前窗口和下一窗口重叠部分）
    前14个价格 = 窗口价格[1:]
    前13涨跌 = np.diff(前14个价格)
    前涨幅和 = np.maximum(前13涨跌, 0).sum()
    前跌幅和 = np.maximum(-前13涨跌, 0).sum()

    # 当前RSI：用全部15个价格 → 14个diff
    当前全涨跌 = np.diff(窗口价格)
    当前全涨幅 = np.maximum(当前全涨跌, 0).sum()
    当前全跌幅 = np.maximum(-当前全涨跌, 0).sum()
    当前RS = 当前全涨幅 / 当前全跌幅 if 当前全跌幅 > 0 else float('inf')
    当前RSI = 100 - 100 / (1 + 当前RS) if 当前全跌幅 > 0 else 100

    return _反推求解(当前收盘, 前涨幅和, 前跌幅和, 当前RSI, 目标RSI, 周期)


def 智能反推(收盘价序列, RSI_MA_上一根=None, 周期=14):
    """
    智能反推：根据当前RSI位置自动选择目标RSI

    传入:
        收盘价序列   - 至少15个前复权收盘价
        RSI_MA_上一根 - 上一根K线的RSI_MA值 (必须提供，用于MA上穿判断)
        周期         - RSI周期，默认14

    传出:
        字典 {目标价位, 涨跌方向, 涨跌幅度, 当前RSI,
              目标RSI, 选择逻辑, RSI_MA_上一根, ...}
    """
    价格 = np.array(收盘价序列, dtype=float)
    if len(价格) < 周期 + 1:
        return {"目标价位": None, "涨跌方向": "数据不足",
                "说明": f"至少需要{周期+1}个价格，传入{len(价格)}个"}

    # 先算当前RSI
    窗口价格 = 价格[-(周期 + 1):]
    当前收盘 = 窗口价格[-1]
    前14个价格 = 窗口价格[1:]
    前13涨跌 = np.diff(前14个价格)
    前涨幅和 = np.maximum(前13涨跌, 0).sum()
    前跌幅和 = np.maximum(-前13涨跌, 0).sum()

    当前全涨跌 = np.diff(窗口价格)
    当前全涨幅 = np.maximum(当前全涨跌, 0).sum()
    当前全跌幅 = np.maximum(-当前全涨跌, 0).sum()
    当前RS = 当前全涨幅 / 当前全跌幅 if 当前全跌幅 > 0 else float('inf')
    当前RSI = 100 - 100 / (1 + 当前RS) if 当前全跌幅 > 0 else 100

    # 根据当前RSI位置选择目标
    目标RSI, 选择逻辑 = _选择目标RSI(当前RSI, RSI_MA_上一根)

    if 目标RSI is None:
        return {
            "目标价位": None,
            "涨跌方向": "无买入信号",
            "涨跌幅度": None,
            "当前RSI": round(当前RSI, 4),
            "目标RSI": None,
            "选择逻辑": 选择逻辑,
            "RSI_MA_上一根": RSI_MA_上一根,
        }

    结果 = _反推求解(当前收盘, 前涨幅和, 前跌幅和, 当前RSI, 目标RSI, 周期)
    结果["选择逻辑"] = 选择逻辑
    结果["目标RSI"] = 目标RSI
    结果["RSI_MA_上一根"] = RSI_MA_上一根
    return 结果


def _选择目标RSI(当前RSI, RSI_MA_上一根=None):
    """
    根据当前RSI位置，自动选择下一个要反推的目标RSI

    目标信号优先级（与买入规则一致）:
      1. RSI上穿20   (优先级0)
      2. RSI上穿30   (优先级1)
      3. RSI上穿均线 (优先级2)
      4. RSI上穿70   (优先级3)

    描述会显示当前RSI已上穿的阈值，方便交易员判断位置
    """
    # 阈值定义
    RSI_20 = 20
    RSI_30 = 30
    RSI_70 = 70

    # 构建"已上穿"描述
    已上穿 = []
    if 当前RSI >= RSI_20:
        已上穿.append('20')
    if RSI_MA_上一根 is not None and 当前RSI >= RSI_MA_上一根:
        已上穿.append(f'均线({RSI_MA_上一根:.0f})')
    if 当前RSI >= RSI_30:
        已上穿.append('30')
    已上穿文本 = f"(已上穿{'/'.join(已上穿)}) " if 已上穿 else ''

    if 当前RSI < RSI_20:
        return RSI_20, f"RSI({当前RSI:.2f}) < 20 → 反推RSI上穿20"

    if RSI_MA_上一根 is not None and RSI_20 <= 当前RSI < RSI_MA_上一根:
        return RSI_MA_上一根, f"RSI({当前RSI:.2f}) < MA_prev({RSI_MA_上一根:.1f}){已上穿文本}反推RSI上穿均线"

    if RSI_20 <= 当前RSI < RSI_30:
        return RSI_30, f"RSI({当前RSI:.2f}) < 30{已上穿文本}反推RSI上穿30"

    if RSI_30 <= 当前RSI < RSI_70:
        return RSI_70, f"RSI({当前RSI:.2f}) < 70{已上穿文本}反推RSI上穿70"

    return None, f"RSI({当前RSI:.2f}) ≥ 70 → 超买区{已上穿文本}无买入信号"


def _反推求解(当前收盘, 前涨幅和, 前跌幅和, 当前RSI, 目标RSI, 周期=14):
    """内部：给定已知量，从目标RSI反推收盘价"""
    # RSI 的反推区间是 (0, 100)。边界值没有有限的 RS，不能参与价格求解；
    # 回放层遇到这类极端数据时应显示“无有效反推价”，不能抛除零异常。
    try:
        目标RSI = float(目标RSI)
    except (TypeError, ValueError):
        return {"目标价位": None, "目标RSI": None, "选择逻辑": "目标RSI无效，跳过反推"}
    if not np.isfinite(目标RSI) or 目标RSI <= 0 or 目标RSI >= 100:
        return {"目标价位": None, "目标RSI": 目标RSI, "选择逻辑": "目标RSI处于边界，跳过反推"}
    目标RS = 目标RSI / (100 - 目标RSI)

    # 情况A：上涨 (新收盘 > 当前收盘)
    # RS = (前涨幅和 + 新涨幅) / 前跌幅和
    # 新收盘 = 当前收盘 + RS × 前跌幅和 - 前涨幅和
    上涨目标 = 当前收盘 + 目标RS * 前跌幅和 - 前涨幅和

    # 情况B：下跌 (新收盘 < 当前收盘)
    # RS = 前涨幅和 / (前跌幅和 + 新跌幅)
    # 新收盘 = 当前收盘 - (前涨幅和/RS - 前跌幅和)
    下跌目标 = 当前收盘 - (前涨幅和 / 目标RS - 前跌幅和)

    if 上涨目标 > 当前收盘:
        return {
            "目标价位": round(上涨目标, 2),
            "涨跌方向": "上涨",
            "涨跌幅度": round(上涨目标 - 当前收盘, 2),
            "当前RSI": round(当前RSI, 4),
            "目标RSI": 目标RSI,
            "目标RS": round(目标RS, 6),
            "前13根涨幅和": round(前涨幅和, 4),
            "前13根跌幅和": round(前跌幅和, 4),
        }
    elif 下跌目标 < 当前收盘:
        return {
            "目标价位": round(下跌目标, 2),
            "涨跌方向": "下跌",
            "涨跌幅度": round(下跌目标 - 当前收盘, 2),
            "当前RSI": round(当前RSI, 4),
            "目标RSI": 目标RSI,
            "目标RS": round(目标RS, 6),
            "前13根涨幅和": round(前涨幅和, 4),
            "前13根跌幅和": round(前跌幅和, 4),
        }
    else:
        return {
            "目标价位": None,
            "涨跌方向": "无解",
            "涨跌幅度": None,
            "当前RSI": round(当前RSI, 4),
            "目标RSI": 目标RSI,
            "目标RS": round(目标RS, 6),
            "前13根涨幅和": round(前涨幅和, 4),
            "前13根跌幅和": round(前跌幅和, 4),
            "说明": "该目标RSI在当前窗口下无可行解",
        }


def 从价格算RSI(收盘价序列, 周期=14):
    """辅助函数：给出一组价格，快速算RSI（验证用）"""
    价格 = np.array(收盘价序列, dtype=float)
    涨跌 = np.diff(价格)
    涨幅 = np.maximum(涨跌, 0)
    跌幅 = np.maximum(-涨跌, 0)
    涨幅均值 = 涨幅.mean()
    跌幅均值 = 跌幅.mean()
    if 跌幅均值 == 0:
        return 100.0
    if 涨幅均值 == 0:
        return 0.0
    RS = 涨幅均值 / 跌幅均值
    return 100 - 100 / (1 + RS)


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    print("=" * 50)
    print("反推因子 — 自检测试")
    print("=" * 50)

    from 数据模块.股票加载器 import 加载股票
    from 策略引擎.rsi import 计算RSI
    from 策略引擎.rsi_ma import 计算RSI均线

    数据 = 加载股票("600519", "双价格合并")
    价格 = 数据['前复权_收盘'].values
    rsi_data = 数据['RSI_14'].values
    rsi_ma_data = 数据['RSI_均线_20'].values

    print("\n" + "=" * 50)
    print("测试1: 直接反推 (给定目标RSI=20)")
    print("=" * 50)
    pos = 67  # 2020-02-03 15:00
    窗口 = 价格[pos - 14:pos + 1]
    结果 = 反推RSI价位(窗口, 目标RSI=20)
    print(f"  当前RSI: {结果['当前RSI']}  (数据={rsi_data[pos]:.2f})")
    print(f"  目标RSI: 20 → 价位 = {结果['目标价位']} ({结果['涨跌方向']}{结果['涨跌幅度']})")
    验证窗口 = np.append(窗口[1:], 结果['目标价位'])
    验证RSI = 从价格算RSI(验证窗口)
    print(f"  验证: RSI={验证RSI:.2f} (应≈20)")

    print("\n" + "=" * 50)
    print("测试2: 智能反推 (根据RSI位置自动选择目标)")
    print("=" * 50)
    for test_pos in [67, 70, 75, 80, 85, 90]:
        if test_pos >= len(价格) - 1:
            break
        test窗 = 价格[test_pos - 14:test_pos + 1]
        rsi_ma_prev = rsi_ma_data[test_pos - 1]  # 用上一根固定的MA
        result = 智能反推(test窗, RSI_MA_上一根=rsi_ma_prev)

        print(f"  位置{test_pos} (RSI={rsi_data[test_pos]:.2f}, MA_prev={rsi_ma_prev:.2f})")
        print(f"    策略: {result['选择逻辑']}")
        if result['目标价位']:
            验证窗 = np.append(test窗[1:], result['目标价位'])
            验证RSI = 从价格算RSI(验证窗)
            print(f"    目标价: {result['目标价位']} ({result['涨跌方向']}{result['涨跌幅度']})  验证RSI={验证RSI:.2f}")
        else:
            print(f"    结果: {result['涨跌方向']}")

    print("\n" + "=" * 50)
    print("测试3: 与买入规则对应关系验证")
    print("=" * 50)
    rsi_prev = 18.94
    for rsi_now, ma_prev in [(19.5, 25.1), (22.5, 30.1), (32.5, 30.1), (55, 30.1), (75, 30.1)]:
        target, logic = _选择目标RSI(rsi_now, ma_prev)
        target_str = f"RSI={target}" if target else "无"
        print(f"  RSI={rsi_now:.1f}, MA_prev={ma_prev:.1f} → {logic} (目标={target_str})")

    print(f"\n✅ 反推因子自检完成")

def 所有反推候选(收盘价序列, RSI_MA_上一根=None, 上一根最高价=None, 周期=14):
    """
    返回所有可能的反推价候选关卡（用于价格突破跟踪）
    
    传入:
        收盘价序列   - list/array，至少(周期+1)=15个前复权收盘价
        RSI_MA_上一根 - 上一根K线的RSI_MA值
        上一根最高价 - 上一根K线的前复权最高价（过滤条件：反推价必须>此值）
        周期         - RSI周期，默认14
    
    传出:
        列表，每个元素是字典 {目标价位, 目标RSI, 关卡名, 是否有效}
        只有在"反推价 > 上一根最高价"且"反推价 > 当前收盘"时才标记有效
    """
    价格 = np.array(收盘价序列, dtype=float)
    if len(价格) < 周期 + 1:
        return []
    
    窗口价格 = 价格[-(周期 + 1):]
    当前收盘 = 窗口价格[-1]
    前14个价格 = 窗口价格[1:]
    前13涨跌 = np.diff(前14个价格)
    前涨幅和 = np.maximum(前13涨跌, 0).sum()
    前跌幅和 = np.maximum(-前13涨跌, 0).sum()
    
    # 计算当前RSI
    当前全涨跌 = np.diff(窗口价格)
    当前全涨幅 = np.maximum(当前全涨跌, 0).sum()
    当前全跌幅 = np.maximum(-当前全涨跌, 0).sum()
    当前RS = 当前全涨幅 / 当前全跌幅 if 当前全跌幅 > 0 else float('inf')
    当前RSI = 100 - 100 / (1 + 当前RS) if 当前全跌幅 > 0 else 100
    
    候选列表 = []
    关卡定义 = [
        (20, "RSI上穿20"),
    ]
    if RSI_MA_上一根 is not None and RSI_MA_上一根 > 当前RSI:
        关卡定义.append((RSI_MA_上一根, "RSI上穿均线"))
    关卡定义.append((30, "RSI上穿30"))
    关卡定义.append((70, "RSI上穿70"))
    
    for 目标RSI, 关卡名 in 关卡定义:
        if 目标RSI is None or 目标RSI <= 当前RSI:
            continue
        
        结果 = 反推RSI价位(收盘价序列, 目标RSI=目标RSI, 周期=周期)
        目标价 = 结果.get('目标价位')
        
        if 目标价 is None:
            continue
        
        # 条件1：反推价必须大于上一根K线的最高价
        高于高价位 = True
        if 上一根最高价 is not None and 目标价 <= 上一根最高价:
            高于高价位 = False
        
        # 条件2：反推价必须大于当前收盘价（上涨方向）
        高于现价 = 目标价 > 当前收盘
        
        是否有效 = 高于高价位 and 高于现价
        
        候选列表.append({
            "目标价位": round(目标价, 2),
            "目标RSI": 目标RSI,
            "关卡名": 关卡名,
            "涨跌方向": 结果.get('涨跌方向'),
            "当前RSI": round(当前RSI, 2),
            "是否有效": 是否有效,
            "高于高价位": 高于高价位,
            "高于现价": 高于现价,
        })
    
    return 候选列表


# ========== 卖出侧反推函数 ==========

def 反推回落价位(收盘价序列, 当前RSI=None, 目标RSI=None, RSI峰值=None, 回落阈值=15, 周期=14):
    """
    反推回落价位：从当前RSI向下回落到目标RSI需要的价格
    用于卖出侧 — 对称于买入侧的反推上穿

    例子: RSI峰值=70, 回落阈值=15 → 目标RSI=55
          当前RSI=60 > 55, 当前收盘=1300
          反推结果 = 价格跌到X元时RSI会到55 → X ≈ 1294
          卖出条件: 最低价 ≤ X → 按X-滑点卖出

    传入:
        收盘价序列 - list/array，至少(周期+1)=15个前复权收盘价
        当前RSI   - 当前RSI值（不传则自动计算）
        目标RSI   - 直接指定目标RSI（如55）
        RSI峰值  - 通过(峰值-阈值)间接指定目标RSI
        回落阈值  - 默认15，和动能衰竭规则一致
        周期     - RSI周期，默认14

    传出:
        字典 {目标价位, 当前RSI, 目标RSI, 涨跌方向, 涨跌幅度, 说明}
    """
    价格 = np.array(收盘价序列, dtype=float)
    if len(价格) < 周期 + 1:
        return {"目标价位": None, "说明": f"至少需要{周期+1}个价格，传入{len(价格)}个"}

    # 如果没传入当前RSI，自动计算
    if 当前RSI is None:
        窗口价格 = 价格[-(周期 + 1):]
        当前全涨跌 = np.diff(窗口价格)
        当前全涨幅 = np.maximum(当前全涨跌, 0).sum()
        当前全跌幅 = np.maximum(-当前全涨跌, 0).sum()
        当前RS = 当前全涨幅 / 当前全跌幅 if 当前全跌幅 > 0 else float('inf')
        当前RSI = 100 - 100 / (1 + 当前RS) if 当前全跌幅 > 0 else 100
    else:
        当前RSI = float(当前RSI)

    # 确定目标RSI
    if 目标RSI is None and RSI峰值 is not None:
        目标RSI = RSI峰值 - 回落阈值

    if 目标RSI is None:
        return {"目标价位": None, "说明": "未指定目标RSI或RSI峰值/回落阈值"}

    if 目标RSI >= 当前RSI:
        return {"目标价位": None, "当前RSI": round(当前RSI, 2), "目标RSI": 目标RSI,
                "说明": f"目标RSI({目标RSI})未低于当前RSI({当前RSI:.2f})，不构成回落信号"}

    结果 = 反推RSI价位(收盘价序列, 目标RSI=目标RSI, 周期=周期)
    结果['当前RSI'] = round(当前RSI, 2)
    结果['目标RSI'] = 目标RSI
    结果['说明'] = f"回落目标: RSI从{当前RSI:.1f}回落至{目标RSI}"
    return 结果
