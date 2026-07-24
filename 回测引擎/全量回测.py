#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全量回测.py — HS300全量回测 (Phase 2 Step 03)
跳过HTML生成，只收集统计结果

用法:
    python 回测引擎/全量回测.py
"""

import os, sys, warnings, time, json
warnings.filterwarnings('ignore')
import pandas as pd
from datetime import datetime

项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 项目根目录)

from 回测引擎.backtest_engine import 跑回测

# 读取HS300列表
def 获取HS300股票():
    hs300_path = os.path.join(项目根目录, '数据模块', 'hs300_list.txt')
    with open(hs300_path) as f:
        lines = [line.strip() for line in f if line.strip()]
    
    股票列表 = []
    for code in lines:
        pure = code.replace("SH_","").replace("SZ_","")
        数据路径 = os.path.join(项目根目录, '数据模块', 'raw', f'{pure}_双价格合并.pkl')
        if os.path.exists(数据路径):
            股票列表.append(pure)
    print(f"有数据的HS300: {len(股票列表)} 只 (共{len(lines)}只)")
    return 股票列表

# 跑全部回测
if __name__ == "__main__":
    开始时间 = time.time()
    print(f"\n{'='*60}")
    print(f"HS300 全量回测")
    print(f"开始时间: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}")
    
    股票列表 = 获取HS300股票()
    初始资金 = 20000000  # 2000万
    
    所有结果 = []
    成功 = 0
    失败 = 0
    耗时预测 = len(股票列表) * 2.5  # 每只约2.5秒
    print(f"预计耗时: {耗时预测/60:.0f}分钟 ({耗时预测:.0f}秒)")
    print()
    
    for idx, 股票代码 in enumerate(股票列表):
        try:
            print(f"[{idx+1}/{len(股票列表)}] {股票代码}...", end=" ", flush=True)
            开始 = time.time()
            结果 = 跑回测(股票代码, 初始资金=初始资金)
            耗时 = time.time() - 开始
            
            if 结果:
                摘要 = {
                    "股票代码": 股票代码,
                    "交易次数": 结果['买入次数'],
                    "卖出次数": 结果['卖出次数'],
                    "胜率": round(结果['胜率'], 1),
                    "平均盈亏": round(结果['平均盈亏'], 2),
                    "总收益率": round(结果['总收益率'], 2),
                    "最终现金": int(结果['最终现金']),
                    "剩余持仓": 结果['剩余持仓'],
                    "耗时": round(耗时, 1),
                }
                所有结果.append(摘要)
                成功 += 1
                print(f"✅ {耗时:.1f}s (交易{结果['买入次数']}笔, 收益{结果['总收益率']:+.2f}%)")
            else:
                失败 += 1
                print(f"❌ 无结果")
        
        except Exception as e:
            失败 += 1
            print(f"❌ {e}")
        
        # 每10只存一次中间结果
        if (idx + 1) % 10 == 0:
            df_temp = pd.DataFrame(所有结果)
            df_temp.to_csv(os.path.join(项目根目录, '10_实验记录', '_全量回测_中间结果.csv'), index=False, encoding='utf-8-sig')
    
    总耗时 = time.time() - 开始时间
    
    # 最终汇总
    print(f"\n{'='*60}")
    print(f"全量回测完成!")
    print(f"{'='*60}")
    print(f"成功: {成功} / 失败: {失败} / 总计: {len(股票列表)}")
    print(f"总耗时: {总耗时/60:.1f}分钟 ({总耗时:.0f}秒)")
    
    if 所有结果:
        df = pd.DataFrame(所有结果)
        
        # 统计指标
        print(f"\n--- 汇总统计 (含税费+LightGBM方案C) ---")
        print(f"{'指标':<20} {'值':>12}")
        print(f"{'='*35}")
        print(f"{'平均交易次数':<20} {df['交易次数'].mean():>12.1f}")
        print(f"{'平均胜率':<20} {df['胜率'].mean():>12.1f}%")
        print(f"{'平均收益率':<20} {df['总收益率'].mean():>12.2f}%")
        print(f"{'中位数收益率':<20} {df['总收益率'].median():>12.2f}%")
        print(f"{'收益率标准差':<20} {df['总收益率'].std():>12.2f}%")
        print(f"{'盈利股票数':<20} {len(df[df['总收益率']>0]):>12} / {len(df)}")
        print(f"{'亏损股票数':<20} {len(df[df['总收益率']<=0]):>12} / {len(df)}")
        print(f"{'最佳收益率':<20} {df['总收益率'].max():>12.2f}%")
        print(f"{'最差收益率':<20} {df['总收益率'].min():>12.2f}%")
        
        # 收益率分布
        print(f"\n--- 收益率分布 ---")
        分档 = [-5, -3, -1, 0, 1, 3, 5, 10]
        for i in range(len(分档)-1):
            lo, hi = 分档[i], 分档[i+1]
            cnt = len(df[(df['总收益率'] > lo) & (df['总收益率'] <= hi)])
            bar = "█" * (cnt // 2)
            print(f"  {lo:+4}% ~ {hi:+4}%: {cnt:>4}只 {bar}")
        
        # 保存结果
        输出路径 = os.path.join(项目根目录, '10_实验记录', f'_全量回测_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
        df.to_csv(输出路径, index=False, encoding='utf-8-sig')
        print(f"\n结果已保存: {输出路径}")
        
        # 打印Top 10 / Bottom 10
        print(f"\n--- 最佳10只 ---")
        print(df.nlargest(10, '总收益率')[['股票代码', '总收益率', '胜率', '交易次数']].to_string(index=False))
        print(f"\n--- 最差10只 ---")
        print(df.nsmallest(10, '总收益率')[['股票代码', '总收益率', '胜率', '交易次数']].to_string(index=False))
    
    print(f"\n{'='*60}")
