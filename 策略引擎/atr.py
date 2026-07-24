# atr.py — 计算ATR (平均真实波幅)
# 功能: 传入K线数据，返回ATR数值列表
# 用途: 止损宽度、站岗价缓冲、峰值回落阈值调整、突破力度判断
#
# 用法:
#   from 策略引擎.atr import 计算ATR, 计算ATR缓冲价, 判断突破力度

import pandas as pd
import numpy as np


def 计算ATR(最高价, 最低价, 收盘价, 周期=14):
    """
    计算ATR (平均真实波幅)
    
    传入:
        最高价 - 最高价序列
        最低价 - 最低价序列
        收盘价 - 收盘价序列
        周期   - ATR计算周期，默认14
    
    传出:
        pandas Series，ATR数值
    """
    
    前收盘 = pd.Series(收盘价).shift(1)
    
    今日振幅 = pd.Series(最高价) - pd.Series(最低价)
    今日最高_昨收 = abs(pd.Series(最高价) - 前收盘)
    今日最低_昨收 = abs(pd.Series(最低价) - 前收盘)
    
    TR = pd.concat([今日振幅, 今日最高_昨收, 今日最低_昨收], axis=1).max(axis=1)
    ATR = TR.rolling(window=周期, min_periods=周期).mean()
    
    return ATR


def 计算ATR缓冲价(站岗价, ATR值, 缓冲倍数=0.5):
    """
    计算ATR缓冲后的卖出价格，防止毛刺K线假跌破
    
    真实卖出点 = 站岗价 - 缓冲倍数 × ATR
    
    传入:
        站岗价   - 设的站岗价
        ATR值    - 当前的ATR值
        缓冲倍数 - 默认0.5
    
    传出: 缓冲后的卖出触发价
    """
    return 站岗价 - 缓冲倍数 * ATR值


def 判断突破力度(价格移动, ATR值):
    """
    判断一根K线的突破力度
    
    价格移动 > 2×ATR  → 真突破，信号加强
    价格移动 < 0.5×ATR → 假突破，信号减弱
    
    传入:
        价格移动 - 本次价格变动幅度
        ATR值    - 当前的ATR值
    
    传出: "真突破" / "普通" / "假突破"
    """
    
    if ATR值 == 0 or pd.isna(ATR值):
        return "普通"
    
    倍数 = abs(价格移动) / ATR值
    
    if 倍数 >= 2:
        return "真突破"
    elif 倍数 <= 0.5:
        return "假突破"
    else:
        return "普通"


def 调整峰值回落阈值(基础阈值, 股票ATR, 市场平均ATR=0.5):
    """
    用ATR动态调整RSI峰值回落阈值
    
    高波动股票: 放宽阈值(不容易误触发)
    低波动股票: 收紧阈值(更快反应)
    
    阈值 = 基础阈值 × (股票ATR / 市场平均ATR)
    """
    if 市场平均ATR <= 0:
        return 基础阈值
    return 基础阈值 * (股票ATR / 市场平均ATR)


if __name__ == "__main__":
    # 自检测试
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    print("=" * 40)
    print("ATR计算 — 自检测试")
    print("=" * 40)
    
    from 数据模块.股票加载器 import 加载股票
    
    数据 = 加载股票("600519", "双价格合并")
    if 数据 is not None:
        atr = 计算ATR(数据['前复权_最高'], 数据['前复权_最低'], 数据['前复权_收盘'], 周期=14)
        
        print(f"\n600519 ATR(14) 计算结果:")
        print(f"  ATR范围: {atr.min():.2f} ~ {atr.max():.2f}")
        print(f"  平均ATR: {atr.mean():.2f}")
        print(f"  最新ATR: {atr.iloc[-1]:.2f}")
        print(f"  NaN数量: {atr.isna().sum()} (前14个是正常的)")
        
        最新收盘 = 数据['前复权_收盘'].iloc[-1]
        最新ATR = atr.iloc[-1]
        缓冲价 = 计算ATR缓冲价(最新收盘, 最新ATR, 0.5)
        print(f"\nATR缓冲价测试:")
        print(f"  假设站岗价: {最新收盘:.2f}")
        print(f"  ATR: {最新ATR:.2f}")
        print(f"  缓冲后卖出价: {缓冲价:.2f}")
        
        print(f"\n突破力度判断测试:")
        print(f"  移动1元: {判断突破力度(1, 最新ATR)}")
        print(f"  移动5元: {判断突破力度(5, 最新ATR)}")
        print(f"  移动20元: {判断突破力度(20, 最新ATR)}")
    
    print("\n✅ ATR计算自检完成")
