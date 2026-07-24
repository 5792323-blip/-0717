# rsi_ma.py — 计算RSI均线 (RSI的移动平均线)
# 功能: 传入RSI数值列表，返回RSI均线数值列表
#
# 用法:
#   from 策略引擎.rsi_ma import 计算RSI均线
#   rsi均线列表 = 计算RSI均线(RSI列表, 周期=20)

import pandas as pd
import numpy as np


def 计算RSI均线(RSI序列, 周期=20):
    """
    计算RSI的简单移动平均线(SMA)
    
    传入:
        RSI序列  - RSI数值列表
        周期     - 均线周期，默认20
    
    传出:
        pandas Series，均线数值，前(周期-1)个值为NaN
    """
    
    rsi = pd.Series(RSI序列)
    均线 = rsi.rolling(window=周期, min_periods=周期).mean()
    
    return 均线


def 判断均线趋势上升(RSI均线, 当前K线位置, 查看K线数=5):
    """
    判断RSI均线是否在持续上升
    
    这是用来过滤"一根阳线拉高MA"的假信号:
    不是看 MA(current) > MA(previous)，而是看
    MA(current) > 前N根中的最低值
    
    传入:
        RSI均线      - RSI均线序列
        当前K线位置   - 当前在第几根K线 (int)
        查看K线数     - 回看多少根K线做对比，默认5
    
    传出:
        True  = 均线在上升趋势中
        False = 均线盘整或下降
    """
    
    if 当前K线位置 < 查看K线数:
        return False
    
    前N根最低 = RSI均线.iloc[当前K线位置 - 查看K线数:当前K线位置 + 1].min()
    当前值 = RSI均线.iloc[当前K线位置]
    
    # 当前值比前N根中的最低值高 → 趋势向上
    return 当前值 > 前N根最低


if __name__ == "__main__":
    # 自检测试
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    print("=" * 40)
    print("RSI均线 — 自检测试")
    print("=" * 40)
    
    from 数据模块.股票加载器 import 加载股票
    from 策略引擎.rsi import 计算RSI
    
    数据 = 加载股票("600519", "双价格合并")
    if 数据 is not None:
        RSI = 计算RSI(数据['前复权_收盘'], 周期=14)
        RSI_MA = 计算RSI均线(RSI, 周期=20)
        
        print(f"RSI均线(20) 计算结果:")
        print(f"  均线范围: {RSI_MA.min():.2f} ~ {RSI_MA.max():.2f}")
        print(f"  NaN数量: {RSI_MA.isna().sum()} (前20个是正常的)")
        print(f"  最新均线值: {RSI_MA.iloc[-1]:.2f}")
        
        # 测试趋势判断
        当前位置 = len(RSI_MA) - 1
        趋势 = 判断均线趋势上升(RSI_MA, 当前位置, 查看K线数=5)
        print(f"\n均线趋势判断(当前位置={当前位置}):")
        print(f"  前5根最低: {RSI_MA.iloc[当前位置-5:当前位置+1].min():.2f}")
        print(f"  当前值: {RSI_MA.iloc[当前位置]:.2f}")
        print(f"  趋势向上: {趋势}")
    
    print("\n✅ RSI均线计算自检完成")
