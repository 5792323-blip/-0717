# rsi.py — 计算RSI指标 (相对强弱指标)
# 功能: 传入收盘价列表，返回RSI数值列表
# 算法: SMA（简单移动平均）
#
# 用法:
#   from 策略引擎.rsi import 计算RSI
#   rsi值列表 = 计算RSI(收盘价列表, 周期=14)

import pandas as pd
import numpy as np


def 计算RSI(收盘价, 周期=14):
    """
    计算RSI指标
    
    传入:
        收盘价  - pandas Series 或 list，前复权收盘价
        周期    - RSI计算周期，默认14
    
    传出:
        pandas Series，RSI数值，前(周期)个值为NaN
    
    说明:
        使用SMA算法：最近14个涨跌幅分别求平均
        RSI = 100 - 100 / (1 + RS)
        RS = 平均涨幅 / 平均跌幅
    """
    
    价格序列 = pd.Series(收盘价)
    
    # 计算每日涨跌
    涨跌 = 价格序列.diff()
    
    # 分开涨幅和跌幅
    涨幅 = 涨跌.clip(lower=0)     # 只保留正数
    跌幅 = -涨跌.clip(upper=0)    # 转成正数
    
    # 正式策略固定使用最近周期个涨跌幅的简单平均。
    平均涨幅 = 涨幅.rolling(window=周期, min_periods=周期).mean()
    平均跌幅 = 跌幅.rolling(window=周期, min_periods=周期).mean()
    
    # 计算RS和RSI
    RS = 平均涨幅 / 平均跌幅
    RSI = 100 - (100 / (1 + RS))
    
    return RSI


if __name__ == "__main__":
    # 自检测试
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    print("=" * 40)
    print("RSI计算 — 自检测试")
    print("=" * 40)
    
    # 构造简单的测试数据
    测试数据 = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11]
    结果 = 计算RSI(测试数据, 周期=5)
    
    print(f"测试数据({len(测试数据)}个): {测试数据}")
    print(f"RSI结果({len(结果)}个): {[round(x,2) if not pd.isna(x) else None for x in 结果]}")
    print(f"有效RSI值: {结果.notna().sum()} 个 (前5个为NaN是正常的)")
    print()
    
    # 加载真实数据测试
    from 数据模块.股票加载器 import 加载股票, 查看数据摘要
    
    数据 = 加载股票("600519", "双价格合并")
    if 数据 is not None:
        rsi = 计算RSI(数据['前复权_收盘'], 周期=14)
        print(f"\n600519 RSI(14) 计算结果:")
        print(f"  最新RSI: {rsi.iloc[-1]:.2f}")
        print(f"  RSI范围: {rsi.min():.2f} ~ {rsi.max():.2f}")
        print(f"  NaN数量: {rsi.isna().sum()} (前14个是正常的)")
    
    print("\n✅ RSI计算自检完成")
