#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
multi_backtest.py — 多股回测，验证LightGBM方案B效果
用便宜的沪深300股票测试仓位调整效果

用法:
    python 回测引擎/multi_backtest.py
"""

import os, sys, warnings
warnings.filterwarnings('ignore')
import pandas as pd
from datetime import datetime

项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 项目根目录)

from 回测引擎.backtest_engine import 跑回测, 保存结果

# 便宜的沪深300股票 (10-15元区间)
回测股票列表 = [
    "000001",  # 平安银行 10.29
    "002736",  # 国信证券 10.35
    "601009",  # 南京银行 10.43
    "600415",  # 小商品城 10.62
    "600919",  # 江苏银行 11.15
    "002532",  # 天山铝业 11.37
    "300251",  # 光线传媒 11.67
    "002493",  # 荣盛石化 11.68
    "600438",  # 通威股份 11.80
    "300122",  # 智飞生物 12.17
    "601058",  # 赛轮轮胎 12.28
    "601012",  # 隆基绿能 12.55
    "601898",  # 中煤能源 12.67
]

初始资金 = 2000000  # 200万，便宜股票可以买很多手

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"多股回测验证 LightGBM 方案B")
    print(f"股票数: {len(回测股票列表)}")
    print(f"初始资金: {初始资金:,}")
    print(f"{'='*60}")
    
    所有结果 = []
    
    for 股票代码 in 回测股票列表:
        try:
            print(f"\n--- 正在回测: {股票代码} ---")
            结果 = 跑回测(股票代码, 初始资金=初始资金)
            if 结果:
                结果['股票代码'] = 股票代码
                所有结果.append(结果)
                保存结果(结果)
        except Exception as e:
            print(f"❌ {股票代码} 回测失败: {e}")
    
    # 汇总
    print(f"\n{'='*60}")
    print(f"回测汇总")
    print(f"{'='*60}")
    
    汇总数据 = []
    for r in 所有结果:
        汇总数据.append({
            '股票代码': r['股票代码'],
            '买入次数': r['买入次数'],
            '卖出次数': r['卖出次数'],
            '胜率': r['胜率'],
            '平均盈亏': f"{r['平均盈亏']:+.2f}%",
            '总收益率': f"{r['总收益率']:+.2f}%",
            '最终现金': r['最终现金'],
            '剩余持仓': r['剩余持仓'],
        })
    
    df = pd.DataFrame(汇总数据)
    print(df.to_string(index=False))
    
    # 总体统计
    if 所有结果:
        平均收益 = sum(r['总收益率'] for r in 所有结果) / len(所有结果)
        总交易 = sum(r['买入次数'] for r in 所有结果)
        总胜率 = sum(r['买入次数'] * r['胜率'] for r in 所有结果) / max(sum(r['买入次数'] for r in 所有结果), 1)
        print(f"\n总体统计:")
        print(f"   平均收益率: {平均收益:+.2f}%")
        print(f"   总交易次数: {总交易}")
        print(f"   加权胜率: {总胜率:.1f}%")
    
    print(f"\n✅ 多股回测完成")
