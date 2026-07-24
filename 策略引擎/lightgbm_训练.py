#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lightgbm_训练.py — Phase 3: LightGBM假突破判断（扩量训练）

流程:
  1. 批量加载多只股票（默认100只）
  2. 对每只股票跑回测 + 收集买入样本
  3. 对每个买入信号，前看20根K线标定真突破/假突破
  4. 聚合训练数据 → LightGBM训练
  5. 保存模型 + 输出特征重要性

用法:
  python 策略引擎/lightgbm_训练.py [股票数量]
  例: python 策略引擎/lightgbm_训练.py 50   (跑50只)
"""

import os, sys, glob, json, warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
from datetime import datetime

# ─── 项目根路径 ───
项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 项目根目录)

from 策略引擎.规则执行器 import 规则执行器


# ============================================================
# 第一步：多股票回测 + 数据收集
# ============================================================
def 跑批量回测(股票列表, 初始资金=20000000):
    """对多只股票跑回测，收集买入样本的特征 + 标签"""
    配置目录 = os.path.join(项目根目录, '1_策略配置')
    所有样本 = []
    
    for idx, 代码 in enumerate(股票列表):
        try:
            from 数据模块.股票加载器 import 加载股票
            数据 = 加载股票(代码, "双价格合并")
            if 数据 is None or len(数据) < 200:
                continue
        except Exception as e:
            continue
        
        # 跑回测
        执行器 = 规则执行器(配置目录)
        执行器.当前现金 = 初始资金
        上一根RSI = 50
        
        for i in range(len(数据)):
            行 = 数据.iloc[i]
            行_copy = 行.copy()
            行_copy['_上一根RSI'] = 上一根RSI
            执行器.每根K线处理(行_copy, i)
            rsi_val = 行.get('RSI_14', 50)
            if not pd.isna(rsi_val):
                上一根RSI = rsi_val
            else:
                上一根RSI = 50
        
        # 获取交易明细
        结果 = 执行器.获取结果()
        交易明细 = 结果['交易明细'] if len(结果['交易明细']) > 0 else 执行器.交易记录器.导出明细()
        if len(交易明细) == 0:
            continue
        
        # 提取买入样本
        买入列表 = 交易明细[交易明细['类型'] == '买入']
        if len(买入列表) == 0:
            continue
        
        for _, 买入 in 买入列表.iterrows():
            买入时间 = str(买入['时间']).strip()
            买入索引 = None
            for k in range(len(数据)):
                if str(数据.iloc[k].name).strip().startswith(买入时间[:16]):
                    买入索引 = k
                    break
            
            if 买入索引 is None or 买入索引 < 10:
                continue
            
            # 特征: 买入时刻的数据
            行 = 数据.iloc[买入索引]
            rsi = 行['RSI_14']
            rsi_ma = 行['RSI_均线_20']
            atr = 行['ATR_14']
            vol = 行['成交量']
            
            if pd.isna(rsi) or pd.isna(rsi_ma):
                continue
            
            # 特征: MA斜率 (前5根和前10根)
            ma_slope_5 = 0.0
            ma_slope_10 = 0.0
            try:
                if 买入索引 >= 5 and not pd.isna(数据.iloc[买入索引-5]['RSI_均线_20']):
                    ma_slope_5 = rsi_ma - 数据.iloc[买入索引-5]['RSI_均线_20']
                if 买入索引 >= 10 and not pd.isna(数据.iloc[买入索引-10]['RSI_均线_20']):
                    ma_slope_10 = rsi_ma - 数据.iloc[买入索引-10]['RSI_均线_20']
            except:
                pass
            
            # 信号类型 (one-hot 编码)
            sig = str(买入.get('信号类型', ''))
            is_20 = 1 if '20' in sig else 0
            is_30 = 1 if '30' in sig else 0
            is_70 = 1 if '70' in sig else 0
            is_ma = 1 if '均线' in sig else 0
            
            # 信号质量分
            quality = 买入.get('信号质量分', 0)
            if pd.isna(quality): quality = 0
            
            # 标签: 前看20根K线, RSI是否始终在MA之上
            end_k = min(买入索引 + 20, len(数据) - 1)
            rsi_values = 数据.iloc[买入索引:end_k+1]['RSI_14'].values
            rsi_ma_values = 数据.iloc[买入索引:end_k+1]['RSI_均线_20'].values
            
            # 过滤掉开头Nan
            valid = ~(pd.isna(rsi_values) | pd.isna(rsi_ma_values))
            if valid.sum() < 3:
                continue
            
            rsi_clean = rsi_values[valid]
            rsi_ma_clean = rsi_ma_values[valid]
            
            # 真突破: RSI始终在MA之上; 假突破: 至少一次RSI<MA
            label = 1 if np.all(rsi_clean >= rsi_ma_clean) else 0
            
            所有样本.append({
                '股票': 代码,
                'RSI': float(rsi),
                'RSI_MA': float(rsi_ma),
                'RSI_MA_差': float(rsi - rsi_ma),
                'ATR': float(atr) if not pd.isna(atr) else 0.0,
                'ATR_占比': float(atr / 行['前复权_收盘'] * 100) if not pd.isna(atr) and 行['前复权_收盘'] > 0 else 0.0,
                '成交量': float(vol) if not pd.isna(vol) else 0.0,
                'MA斜率_5': float(ma_slope_5),
                'MA斜率_10': float(ma_slope_10),
                '信号_上穿20': is_20,
                '信号_上穿30': is_30,
                '信号_上穿70': is_70,
                '信号_上穿均线': is_ma,
                '信号质量分': float(quality),
                'label': label,
            })
        
        if (idx+1) % 10 == 0:
            print(f'   进度: {idx+1}/{len(股票列表)}  |  收集样本: {len(所有样本)}')
    
    return pd.DataFrame(所有样本)


# ============================================================
# 第二步：LightGBM训练
# ============================================================
def 训练LightGBM(样本数据):
    from sklearn.model_selection import train_test_split
    import lightgbm as lgb
    
    if len(样本数据) < 50:
        print(f'样本不足 ({len(样本数据)}), 至少需要50笔')
        return None
    
    # 特征列
    特征列 = [c for c in 样本数据.columns if c not in ('label', '股票')]
    
    X = 样本数据[特征列].values
    y = 样本数据['label'].values
    
    print(f'\n样本总量: {len(X)}')
    print(f'真突破: {y.sum()} ({(y.sum()/len(y)*100):.1f}%)')
    print(f'假突破: {len(y)-y.sum()} ({(1-y.sum()/len(y))*100:.1f}%)')
    
    # 划分训练/测试
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    # LightGBM参数
    params = {
        'objective': 'binary',
        'metric': 'auc',
        'boosting_type': 'gbdt',
        'num_leaves': 31,
        'learning_rate': 0.05,
        'feature_fraction': 0.8,
        'bagging_fraction': 0.8,
        'bagging_freq': 5,
        'verbose': -1,
        'random_state': 42,
        'min_data_in_leaf': 10,
    }
    
    train_data = lgb.Dataset(X_train, label=y_train, feature_name=特征列)
    test_data = lgb.Dataset(X_test, label=y_test, reference=train_data)
    
    model = lgb.train(
        params,
        train_data,
        valid_sets=[test_data],
        num_boost_round=200,
        callbacks=[lgb.early_stopping(20), lgb.log_evaluation(0)]
    )
    
    # 评估
    from sklearn.metrics import (accuracy_score, precision_score,
                                 recall_score, f1_score, roc_auc_score,
                                 confusion_matrix)
    y_pred = (model.predict(X_test) > 0.5).astype(int)
    y_prob = model.predict(X_test)
    
    print(f'\n{"="*50}')
    print(f'LightGBM 评估结果')
    print(f'{"="*50}')
    print(f'准确率:  {accuracy_score(y_test, y_pred):.4f}')
    print(f'精确率:  {precision_score(y_test, y_pred):.4f}')
    print(f'召回率:   {recall_score(y_test, y_pred):.4f}')
    print(f'F1分数:   {f1_score(y_test, y_pred):.4f}')
    print(f'AUC:     {roc_auc_score(y_test, y_prob):.4f}')
    print()
    print('混淆矩阵:')
    cm = confusion_matrix(y_test, y_pred)
    print(f'         预测假突破  预测真突破')
    print(f'实际假突破  {cm[0][0]:5d}       {cm[0][1]:5d}')
    print(f'实际真突破  {cm[1][0]:5d}       {cm[1][1]:5d}')
    
    # 特征重要性
    重要性 = pd.DataFrame({
        '特征': 特征列,
        '重要性': model.feature_importance(importance_type='gain')
    }).sort_values('重要性', ascending=False)
    
    print(f'\n特征重要性 (gain):')
    print(重要性.to_string(index=False))
    
    return model, 特征列, 重要性


# ============================================================
# 主入口
# ============================================================
import argparse
parser = argparse.ArgumentParser(description="LightGBM假突破判断训练")
parser.add_argument("n", type=int, nargs="?", default=100, help="股票数量")
parser.add_argument("--list", type=str, default=None, help="股票代码列表文件路径")
args = parser.parse_args()
n_stocks = args.n
stock_list_path = args.list
if __name__ == '__main__':
    # 解析参数：跑多少只股票
    
    print(f'{"="*50}')
    print(f'LightGBM 假突破判断 — 扩量训练')
    print(f'{"="*50}')
    print(f'目标股票数: {n_stocks}')
    print()
    
    # 获取股票列表
    数据目录 = os.path.join(项目根目录, '数据模块', 'raw')
    所有文件 = sorted(glob.glob(os.path.join(数据目录, "*_双价格合并.pkl")))
    
    if stock_list_path:
        # 加载指定的股票列表文件
        abs_list_path = stock_list_path if os.path.isabs(stock_list_path) else os.path.join(项目根目录, stock_list_path)
        with open(abs_list_path, "r", encoding="utf-8") as f:
            指定股票 = [line.strip() for line in f if line.strip()]
        # 过滤出有数据的股票
        股票列表 = []
        for code in 指定股票:
            clean_code = code.split("_")[-1]  # 去掉 SH_ / SZ_ 前缀
            if os.path.exists(os.path.join(数据目录, f"{clean_code}_双价格合并.pkl")):
                股票列表.append(clean_code)
        print(f"指定列表: {len(指定股票)} 只, 有数据: {len(股票列表)} 只")
    else:
        所有股票 = [os.path.basename(f).split('_')[0] for f in 所有文件]
        print(f'可用股票: {len(所有股票)} 只')
        股票列表 = 所有股票[:n_stocks]
    # 取前N只
    print(f'本次训练: {len(股票列表)} 只')
    print()
    
    # 第一步：跑批量回测收集样本
    print('▶ 开始批量回测收集样本...')
    开始时间 = datetime.now()
    样本数据 = 跑批量回测(股票列表)
    耗时 = (datetime.now() - 开始时间).total_seconds()
    print(f'\n样本收集完成 ({耗时:.1f}秒)')
    print(f'总样本: {len(样本数据)}')
    
    if len(样本数据) < 50:
        print('样本不足50笔，无法训练')
        sys.exit(1)
    
    # 保存样本数据
    时间戳 = datetime.now().strftime('%Y%m%d_%H%M%S')
    样本路径 = os.path.join(项目根目录, '10_实验记录', f'lightgbm_样本_{时间戳}.csv')
    样本数据.to_csv(样本路径, index=False, encoding='utf-8-sig')
    print(f'样本已保存: {样本路径}')
    
    # 第二步：训练LightGBM
    print('\n▶ 开始LightGBM训练...')
    结果 = 训练LightGBM(样本数据)
    
    if 结果 is None:
        sys.exit(1)
    
    model, 特征列, 重要性 = 结果
    
    # 保存模型
    模型路径 = os.path.join(项目根目录, '10_实验记录', f'lightgbm_模型_{时间戳}.txt')
    model.save_model(模型路径)
    print(f'\n模型已保存: {模型路径}')
    
    # 保存特征重要性
    重要性路径 = os.path.join(项目根目录, '10_实验记录', f'lightgbm_特征_{时间戳}.csv')
    重要性.to_csv(重要性路径, index=False, encoding='utf-8-sig')
    print(f'特征重要性: {重要性路径}')
    
    print(f'\n{"="*50}')
    print(f'Phase 3 Step 01 完成')
    print(f'{"="*50}')
    print(f'股票: {len(股票列表)} 只')
    print(f'样本: {len(样本数据)} 笔')
    auc_val = model.best_score['valid_0']['auc'] if hasattr(model, 'best_score') else 'N/A'
    print(f'AUC: {auc_val}')
    print(f'模型: {模型路径}')
