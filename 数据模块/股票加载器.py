# 股票加载器.py
# 功能: 加载单只股票的K线数据，同时返回前复权(算指标)和不复权(成交价)
# 用法: from 数据模块.股票加载器 import 加载股票
#
# 数据来源: 3_数据/raw/ (已清洗的PKL文件)
# 支持格式: 前复权QFQ + 不复权BFQ 双价格对齐

import os
import pandas as pd
import numpy as np

# 数据目录 — 当前文件所在目录下的 raw/
当前目录 = os.path.dirname(os.path.abspath(__file__))
数据目录 = os.path.join(当前目录, 'raw')


def 加载股票(股票代码="600519", 数据来源="双价格合并"):
    """
    加载单只股票的清洗后数据
    
    传入:
        股票代码  - 股票代码，如 "600519"
        数据来源  - "前复权" / "不复权" / "双价格合并"(默认，推荐)
    
    传出:
        pandas DataFrame，包含 K线数据
        如果没有找到数据，返回 None
    """
    
    文件名对照 = {
        "双价格合并": f"{股票代码}_双价格合并.pkl",
        "前复权":     f"{股票代码}_前复权_清洗后.pkl",
        "不复权":     f"{股票代码}_不复权_清洗后.pkl",
    }
    
    文件名 = 文件名对照.get(数据来源)
    if 文件名 is None:
        print(f"错误: 未知的数据来源 '{数据来源}'，可选: 前复权, 不复权, 双价格合并")
        return None
    
    文件路径 = os.path.join(数据目录, 文件名)
    
    if not os.path.exists(文件路径):
        print(f"错误: 找不到文件 {文件路径}")
        print(f"提示: 请先运行数据清洗，或确认股票代码是否正确")
        return None
    
    数据 = pd.read_pickle(文件路径)
    print(f"已加载: {文件名} ({len(数据)} 行)")
    
    return 数据


def 查看数据摘要(数据):
    """
    打印数据的基本信息，方便快速了解数据质量
    
    传入: 加载股票() 返回的 DataFrame
    """
    
    if 数据 is None or len(数据) == 0:
        print("数据为空")
        return
    
    print("=" * 50)
    print("数据摘要")
    print("=" * 50)
    print(f"行数: {len(数据)}")
    print(f"列名: {list(数据.columns)}")
    print(f"索引: {数据.index.name}")
    
    if '日期' in 数据.columns:
        print(f"时间范围: {数据['日期'].min()} ~ {数据['日期'].max()}")
    
    if '前复权_收盘' in 数据.columns:
        print(f"前复权价格: {数据['前复权_收盘'].min():.2f} ~ {数据['前复权_收盘'].max():.2f}")
        print(f"不复权价格: {数据['不复权_收盘'].min():.2f} ~ {数据['不复权_收盘'].max():.2f}")
    elif '收盘价' in 数据.columns:
        print(f"收盘价范围: {数据['收盘价'].min():.2f} ~ {数据['收盘价'].max():.2f}")
    
    # 检查缺失值
    缺失总数 = 数据.isna().sum().sum()
    if 缺失总数 > 0:
        print(f"⚠️  存在 {缺失总数} 个缺失值")
        for 列 in 数据.columns:
            缺失 = 数据[列].isna().sum()
            if 缺失 > 0:
                print(f"    {列}: {缺失} 个缺失")
    else:
        print("缺失值: ✅ 无")
    
    print("=" * 50)


def 获取时间范围(数据, 开始日期=None, 结束日期=None):
    """
    按日期范围筛选数据
    
    传入:
        数据     - 加载股票() 返回的 DataFrame
        开始日期 - 如 "2024-01-01"，None=不限制
        结束日期 - 如 "2024-12-31"，None=不限制
    
    传出: 筛选后的 DataFrame
    """
    
    if 数据 is None or len(数据) == 0:
        return 数据
    
    结果 = 数据.copy()
    
    if 开始日期 is not None:
        结果 = 结果[结果['日期'] >= 开始日期]
    
    if 结束日期 is not None:
        结果 = 结果[结果['日期'] <= 结束日期]
    
    print(f"时间筛选: {开始日期 or '不限'} ~ {结束日期 or '不限'} → {len(结果)} 行")
    return 结果


# 测试代码（直接运行此文件时执行）
if __name__ == "__main__":
    print("=" * 50)
    print("股票加载器 — 自检测试")
    print("=" * 50)
    
    # 测试加载双价格合并数据
    数据 = 加载股票("600519", "双价格合并")
    查看数据摘要(数据)
    
    if 数据 is not None:
        # 测试按时间筛选
        部分 = 获取时间范围(数据, "2025-01-01", "2025-06-30")
        print(f"\n前3行数据:")
        print(部分[[
            '日期', '前复权_收盘', '不复权_收盘', 'RSI_14', 'ATR_14'
        ]].head(3))
        print(f"\n后3行数据:")
        print(部分[[
            '日期', '前复权_收盘', '不复权_收盘', 'RSI_14', 'ATR_14'
        ]].tail(3))
    
    print("\n✅ 股票加载器自检完成")
