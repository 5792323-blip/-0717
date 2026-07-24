#!/usr/bin/env python3
# 数据加工器.py — 从15min原始数据加工为策略可用的60min双价格合并格式
# 功能: 
#   1. 读取新数据的15min parquet
#   2. 聚合为60min K线
#   3. 计算前复权价(用adj_factor)
#   4. 计算RSI_14, RSI_均线_20, ATR_14
#   5. 数据清洗(去重/补缺/异常标记)
#   6. 保存为 {股票代码}_双价格合并.pkl
#
# 用法:
#   python 数据模块/数据加工器.py                                  # 只处理600519
#   python 数据模块/数据加工器.py --all                            # 处理全部股票
#   python 数据模块/数据加工器.py --codes 600519.SH 000001.SZ      # 指定股票

import os, sys, glob, time
import pandas as pd
import numpy as np
from datetime import datetime

项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 项目根目录)

# ========== 配置 ==========
RAW_DIR = os.path.join(项目根目录, '数据模块', 'raw')  # 输出目录
NEW_DATA_DIR = os.path.expanduser('~/Desktop/A数据/parquet格式行情数据')

# 选择最新数据源
if os.path.exists(os.path.join(NEW_DATA_DIR, '行情数据更新到20260703')):
    DATA_SOURCE = os.path.join(NEW_DATA_DIR, '行情数据更新到20260703')
elif os.path.exists(os.path.join(NEW_DATA_DIR, '行情数据更新至2026.7.10')):
    DATA_SOURCE = os.path.join(NEW_DATA_DIR, '行情数据更新至2026.7.10')
else:
    DATA_SOURCE = NEW_DATA_DIR

STOCK_15MIN_DIR = os.path.join(DATA_SOURCE, 'stock_15min')


# ========== 核心算法 ==========

def 聚合60分钟(df_15min):
    """
    将15min数据聚合为60min
    每天17根15min → 4根60min
    分组: 5根(09:30~10:30) + 4根(10:30~11:30) + 4根(13:00~14:00) + 4根(14:00~15:00)
    注意: 第一组跳过09:30集合竞价K线，用后面4根聚合(09:45~10:30)
    """
    df = df_15min.copy()
    df = df.sort_values(['trade_date', 'trade_time'])
    
    # 生成每天序号
    df['seq'] = df.groupby('trade_date').cumcount()
    
    # 60min分组：跳过第0根(09:30集合竞价)
    def get_group(seq):
        if seq == 0: return -1, None  # 跳过集合竞价
        elif seq <= 4: return 0, '10:30'   # 1-4 → 10:30
        elif seq <= 8: return 1, '11:30'   # 5-8 → 11:30
        elif seq <= 12: return 2, '14:00'  # 9-12 → 14:00
        elif seq <= 16: return 3, '15:00'  # 13-16 → 15:00
        else: return -1, None
    
    group_info = df['seq'].apply(lambda x: get_group(x))
    df['60min_group'] = [g for g, _ in group_info]
    df['60min_time'] = [t for _, t in group_info]
    df = df[df['60min_group'] >= 0].copy()
    
    # 检查每组完整性（必须4根）
    group_counts = df.groupby(['trade_date', '60min_group']).size()
    valid_groups = group_counts[group_counts == 4].reset_index()[['trade_date', '60min_group']]
    df = df.merge(valid_groups, on=['trade_date', '60min_group'])
    
    # 聚合
    df60 = df.groupby(['trade_date', '60min_group']).agg(
        开盘=('open', 'first'),
        最高=('high', 'max'),
        最低=('low', 'min'),
        收盘=('close', 'last'),
        成交量=('vol', 'sum'),
        成交额=('amount', 'sum'),
        adj_factor=('adj_factor', 'last'),
        时间=('60min_time', 'first'),
    ).reset_index()
    
    df60['完整时间'] = pd.to_datetime(df60['trade_date'].astype(str) + ' ' + df60['时间'])
    return df60


def 计算前复权(df60):
    """用adj_factor计算前复权价格"""
    df = df60.copy()
    latest_adj = df['adj_factor'].iloc[-1]
    
    for col in ['开盘', '最高', '最低', '收盘']:
        df[f'前复权_{col}'] = (df[col] * latest_adj / df['adj_factor']).round(4)
        df[f'不复权_{col}'] = df[col].round(4)
    
    return df, latest_adj


def 计算RSI(close_prices, period=14):
    """计算RSI"""
    prices = pd.Series(close_prices).astype(float)
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return rsi.values


def 计算RSI_MA(rsi_values, period=20):
    """计算RSI均线"""
    return pd.Series(rsi_values).rolling(window=period, min_periods=period).mean().values


def 计算ATR(df60, period=14):
    """计算ATR (True Range的滑动平均)"""
    high = df60['前复权_最高'].values.astype(float)
    low = df60['前复权_最低'].values.astype(float)
    close = df60['前复权_收盘'].values.astype(float)
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]  # 第一根用自身
    
    tr = np.maximum(high - low, 
         np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    
    atr = pd.Series(tr).rolling(window=period, min_periods=period).mean().values
    return atr


def 清洗数据(df):
    """数据清洗：去重/异常值标记/填充"""
    df = df.copy()
    
    # 1. 去重（按时间排序后去重）
    df = df.drop_duplicates(subset=['完整时间'], keep='first')
    
    # 2. 按时间排序
    df = df.sort_values('完整时间').reset_index(drop=True)
    
    # 3. 标记异常（涨跌停/价格异常）
    df['异常标记'] = ''
    if len(df) > 0:
        pct = df['前复权_收盘'].pct_change() * 100
        df.loc[pct.abs() > 20, '异常标记'] = '涨跌幅异常>20%'
    
    # 4. 检查缺失值。价格缺失不能前值填充，否则会伪造可交易K线。
    required_cols = ['前复权_开盘', '前复权_最高', '前复权_最低', '前复权_收盘',
                     '不复权_开盘', '不复权_最高', '不复权_最低', '不复权_收盘']
    for col in required_cols:
        if col in df.columns:
            df.loc[df[col].isna(), '异常标记'] = '价格缺失'
    
    return df


def 加工单只股票(股票代码_完整):
    """
    加工单只股票数据
    股票代码_完整: 如 "600519.SH"
    """
    ts_code = 股票代码_完整
    股票代码 = ts_code.split('.')[0]  # "600519"
    
    # 确定15min文件路径
    parquet_file = os.path.join(STOCK_15MIN_DIR, f'{ts_code}.parquet')
    if not os.path.exists(parquet_file):
        parquet_file = os.path.join(STOCK_15MIN_DIR, f'{ts_code}(1).parquet')
    if not os.path.exists(parquet_file):
        return None, f"找不到 {ts_code} 的15min数据"
    
    try:
        # 1. 加载15min数据
        df15 = pd.read_parquet(parquet_file)
        
        # 2. 过滤：只保留2020年后的数据（策略回测用）
        df15 = df15[df15.index.get_level_values('trade_date') >= '2020-01-01'].copy()
        if len(df15) == 0:
            return None, f"{ts_code} 2020年后无数据"
        
        df15 = df15.reset_index()
        
        # 3. 聚合为60min
        df60 = 聚合60分钟(df15)
        if len(df60) == 0:
            return None, f"{ts_code} 聚合后无数据"
        
        # 4. 计算前复权
        df60, latest_adj = 计算前复权(df60)
        
        # 5. 计算RSI
        df60['RSI_14'] = 计算RSI(df60['前复权_收盘'].values, period=14)
        
        # 6. 计算RSI_MA
        df60['RSI_均线_20'] = 计算RSI_MA(df60['RSI_14'].values, period=20)
        
        # 7. 计算ATR
        df60['ATR_14'] = 计算ATR(df60, period=14)
        
        # 8. 日期和股票代码
        df60['日期'] = df60['trade_date'].apply(lambda x: x.strftime('%Y-%m-%d') if hasattr(x, 'strftime') else str(x)[:10])
        df60['股票代码'] = f'SH_{股票代码}' if ts_code.endswith('.SH') else f'SZ_{股票代码}'
        
        # 9. 清洗
        df60 = 清洗数据(df60)
        
        # 10. 整理输出列
        输出列 = ['日期', '股票代码', 
                '前复权_开盘', '前复权_最高', '前复权_最低', '前复权_收盘',
                '成交量', '成交额', 'RSI_14', 'RSI_均线_20', 'ATR_14', '异常标记',
                '不复权_开盘', '不复权_最高', '不复权_最低', '不复权_收盘',
                '不复权_成交量']
        
        # 成交量统一用不复权的
        df60['不复权_成交量'] = df60['成交量']
        df60['成交量'] = df60['成交量'].astype(int)
        df60['成交额'] = df60['成交额'].astype(int)
        
        result = df60[输出列].copy()
        
        # 设置索引为完整时间
        result.index = pd.to_datetime(df60['完整时间'])
        result.index.name = '完整时间'
        
        return result, None
    
    except Exception as e:
        return None, str(e)


def 保存数据(df, 股票代码):
    """保存为pkl文件"""
    os.makedirs(RAW_DIR, exist_ok=True)
    文件路径 = os.path.join(RAW_DIR, f'{股票代码}_双价格合并.pkl')
    df.to_pickle(文件路径)
    size_mb = os.path.getsize(文件路径) / 1024 / 1024
    return 文件路径, size_mb


# ========== 主逻辑 ==========

def 主程序(股票列表=None):
    """
    主程序入口
    
    传入:
        股票列表 - 如 ["600519.SH", "000001.SZ"]，None=只处理600519
    """
    print(f"\n{'='*50}")
    print(f"数据加工器")
    print(f"数据源: {STOCK_15MIN_DIR}")
    print(f"输出: {RAW_DIR}")
    print(f"{'='*50}\n")
    
    if not os.path.exists(STOCK_15MIN_DIR):
        print(f"❌ 找不到15min数据目录: {STOCK_15MIN_DIR}")
        return
    
    # 确定要处理的股票列表
    if 股票列表 is None:
        股票列表 = ["600519.SH"]
    
    成功 = 0
    失败 = 0
    开始时间 = time.time()
    
    for i, ts_code in enumerate(股票列表):
        简称 = ts_code.split('.')[0]
        print(f"  [{i+1}/{len(股票列表)}] {ts_code} ... ", end='', flush=True)
        
        df, error = 加工单只股票(ts_code)
        if df is not None:
            路径, 大小 = 保存数据(df, 简称)
            print(f"✅ {len(df)}行 {大小:.1f}MB")
            成功 += 1
        else:
            print(f"❌ {error}")
            失败 += 1
    
    耗时 = time.time() - 开始时间
    print(f"\n{'='*50}")
    print(f"完成: {成功}成功 / {失败}失败 ({耗时:.1f}秒)")
    print(f"{'='*50}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='数据加工器')
    parser.add_argument('--all', action='store_true', help='处理全部股票')
    parser.add_argument('--codes', nargs='+', default=['600519.SH'], help='指定股票代码列表')
    args = parser.parse_args()
    
    if args.all:
        # 扫描全部15min文件
        files = sorted(glob.glob(os.path.join(STOCK_15MIN_DIR, '*.parquet')))
        股票列表 = [os.path.basename(f).replace('.parquet', '').replace('(1)', '') for f in files]
        股票列表 = sorted(set(股票列表))
        print(f"扫描到 {len(股票列表)} 只股票")
        主程序(股票列表)
    else:
        主程序(args.codes)
