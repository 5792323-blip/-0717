#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
predictor.py — LightGBM模型推理模块
加载已训练好的模型，在回测时对买入信号做假突破预测

用法:
  from 策略引擎.predictor import LightGBM预测器
  预测器 = LightGBM预测器(模型路径)
  概率 = 预测器.预测(特征字典)
"""

import os, sys, warnings, glob
warnings.filterwarnings('ignore')
import pandas as pd
import numpy as np

项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class LightGBM预测器:
    """加载LightGBM模型，对买入信号预测真突破概率"""
    
    def __init__(self, 模型路径=None):
        self.model = None
        self.特征列 = None
        
        if 模型路径 is None:
            # 自动找最新训练的模型
            实验目录 = os.path.join(项目根目录, '10_实验记录')
            # 找最新模型（按修改时间排序，平衡模型优先）
            模型文件 = glob.glob(os.path.join(实验目录, 'lightgbm_*模型_*.txt'))
            if 模型文件:
                模型文件.sort(key=os.path.getmtime)
                模型路径 = 模型文件[-1]
        
        if 模型路径 and os.path.exists(模型路径):
            import lightgbm as lgb
            self.model = lgb.Booster(model_file=模型路径)
            self.特征列 = self.model.feature_name()
            print(f'[预测器] 已加载模型: {os.path.basename(模型路径)}')
            print(f'[预测器] 特征数: {len(self.特征列)}')
        else:
            print(f'[预测器] ⚠️ 未找到模型文件，返回默认值')
    
    def 预测(self, rsi=None, rsi_ma=None, atr=None, volume=None,
             ma_slope_5=None, ma_slope_10=None, 信号类型='',
             信号质量分=0.0, 前复权收盘=None):
        """
        预测买入信号是真突破(1)还是假突破(0)
        
        传入:
            rsi          - 当前RSI值
            rsi_ma       - 当前RSI_MA值
            atr          - 当前ATR值
            volume       - 当前成交量
            ma_slope_5   - MA前5根斜率
            ma_slope_10  - MA前10根斜率
            信号类型      - 'RSI上穿20' / 'RSI上穿30' / 'RSI上穿均线' / 'RSI上穿70'
            信号质量分    - 0~1
            前复权收盘    - 前复权收盘价（用于计算ATR占比）
        
        传出:
            {
                '真突破概率': 0~1,
                '是真突破': True/False,
                '置信度': '高/中/低',
            }
        """
        if self.model is None:
            return {'真突破概率': 0.5, '是真突破': False, '置信度': '低'}
        
        # 特征工程
        features = {}
        features['RSI'] = float(rsi) if rsi else 50.0
        features['RSI_MA'] = float(rsi_ma) if rsi_ma else 50.0
        features['RSI_MA_差'] = float(rsi - rsi_ma) if (rsi and rsi_ma) else 0.0
        features['ATR'] = float(atr) if atr else 0.0
        atr_pct = 0.0
        if atr and 前复权收盘 and 前复权收盘 > 0:
            atr_pct = float(atr / 前复权收盘 * 100)
        features['ATR_占比'] = atr_pct
        features['成交量'] = float(volume) if volume else 0.0
        features['MA斜率_5'] = float(ma_slope_5) if ma_slope_5 else 0.0
        features['MA斜率_10'] = float(ma_slope_10) if ma_slope_10 else 0.0
        
        sig = str(信号类型)
        features['信号_上穿20'] = 1 if '20' in sig else 0
        features['信号_上穿30'] = 1 if '30' in sig else 0
        features['信号_上穿70'] = 1 if '70' in sig else 0
        features['信号_上穿均线'] = 1 if '均线' in sig else 0
        features['信号质量分'] = float(信号质量分) if 信号质量分 else 0.0
        
        # 按模型期望的特征顺序排列
        X = np.array([[features.get(col, 0.0) for col in self.特征列]])
        概率 = self.model.predict(X)[0]
        
        # 置信度
        if 概率 > 0.7:
            置信度 = '高'
        elif 概率 > 0.5:
            置信度 = '中'
        elif 概率 > 0.3:
            置信度 = '低'
        else:
            置信度 = '很低'
        
        return {
            '真突破概率': float(概率),
            '是真突破': 概率 > 0.5,
            '置信度': 置信度,
        }


if __name__ == '__main__':
    # 自检
    print('=' * 50)
    print('Predictor 自检')
    print('=' * 50)
    
    预测器 = LightGBM预测器()
    if 预测器.model is None:
        print('⚠️ 无模型文件，只做API测试')
    else:
        # 模拟一个买入信号
        结果 = 预测器.预测(
            rsi=25, rsi_ma=30, atr=15, volume=5000000,
            ma_slope_5=1.5, ma_slope_10=3.2,
            信号类型='RSI上穿20', 信号质量分=0.75,
            前复权收盘=1000
        )
        print(f'预测结果: {结果}')
