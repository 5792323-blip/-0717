#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# market_state.py — 大盘状态分类器 (独立小程序)
#
# 功能: 加载HS300日K线 → 判断当前状态
#   进攻: MA斜率上升且>0 / 防守: MA斜率持续下降
#   震荡: 价格在MA上下波动 / 收缩: ATR持续缩小
#
# 输出: 进攻模式 / 震荡模式 / 防守模式 / 收缩模式

import os, pandas as pd, numpy as np
from 因子模块.因子基类 import 因子基类

项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class 大盘状态(因子基类):
    """加载HS300日K线，判断当前大盘状态"""
    
    def __init__(self, 参数=None):
        super().__init__(参数)
        self.名称 = "大盘状态"
        self.当前状态 = "震荡模式"
        self.HS300数据 = None
        self._加载HS300()
    
    def _加载HS300(self):
        路径 = os.path.join(项目根目录, '数据模块', '大盘数据', 'hs300_日K线.pkl')
        if os.path.exists(路径):
            try:
                self.HS300数据 = pd.read_pickle(路径)
                self.HS300数据['date'] = pd.to_datetime(self.HS300数据['date'])
                self.HS300数据.sort_values('date', inplace=True)
                # 计算MA和斜率
                self.HS300数据['MA20'] = self.HS300数据['close'].rolling(20).mean()
                self.HS300数据['MA斜率'] = self.HS300数据['MA20'].diff(5)
                self.HS300数据['ATR'] = self.HS300数据['close'].rolling(14).std()
                print(f"[大盘状态] ✅ 已加载HS300 ({len(self.HS300数据)}行)")
            except Exception as e:
                print(f"[大盘状态] ⚠️ 加载失败: {e}")
        else:
            print(f"[大盘状态] ⚠️ 无HS300数据")
    
    def _判断状态(self, 当前日期):
        if self.HS300数据 is None:
            return "震荡模式"
        
        # 找最近的数据
        当前日期 = pd.to_datetime(当前日期)
        历史数据 = self.HS300数据[self.HS300数据['date'] <= 当前日期]
        当天 = 历史数据.iloc[-1] if len(历史数据) > 0 else None
        if 当天 is None:
            return "震荡模式"
        
        MA斜率 = 当天.get('MA斜率', 0)
        if pd.isna(MA斜率):
            return "震荡模式"
        
        进攻阈值 = self.参数.get('进攻阈值', 1.5)
        防守阈值 = self.参数.get('防守阈值', -1.5)
        
        if MA斜率 > 进攻阈值:
            return "进攻模式"
        elif MA斜率 < 防守阈值:
            return "防守模式"
        else:
            return "震荡模式"
    
    def 每根K线处理(self, K线数据, 全局状态) -> dict:
        日期 = K线数据.get('日期', '')
        self.当前状态 = self._判断状态(日期)
        # 更新全局状态
        if 全局状态 is not None:
            全局状态['大盘状态'] = self.当前状态
        return {"结果": self.当前状态}
    
    def 买入前检查(self, K线数据, 全局状态) -> dict:
        状态 = self.当前状态
        if 状态 == "防守模式" or 状态 == "收缩模式":
            return {"允许买入": False, "质量分调整": 0.2, "说明": f"大盘{状态}，禁止买入"}
        elif 状态 == "进攻模式":
            return {"允许买入": True, "质量分调整": 1.0, "说明": f"大盘{状态}，鼓励买入"}
        else:
            return {"允许买入": True, "质量分调整": 0.5, "说明": f"大盘{状态}，谨慎买入"}
    
    def 重置(self):
        self.当前状态 = "震荡模式"


if __name__ == "__main__":
    # 自检
    因子 = 大盘状态()
    模拟K线 = {"日期": "2024-01-01"}
    结果 = 因子.每根K线处理(模拟K线, None)
    print(f"大盘状态: {结果}")
    买入检查 = 因子.买入前检查(模拟K线, {"大盘状态": "震荡模式"})
    print(f"买入检查: {买入检查}")
    print("✅ market_state 自检完成")
