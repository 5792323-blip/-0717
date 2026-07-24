#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# divergence.py — RSI背离检测 (独立小程序)
#
# 功能:
#   顶背离: 价格在近期高点附近(2%内), 但RSI远低于近期高点(↓10点+) → 拦截买入
#   底背离: 价格在近期低点附近(2%内), 但RSI远高于近期低点(↑10点+) → 加强买入

import numpy as np
from 因子模块.因子基类 import 因子基类

class RSI背离检测(因子基类):
    """检测RSI顶背离/底背离，用于买入过滤"""
    
    def __init__(self, 参数=None):
        super().__init__(参数)
        self.名称 = "RSI背离检测"
        self.价格历史 = []
        self.RSI历史 = []
        self.前看K线数 = self.参数.get('前看K线数', 20)
        self.有底背离 = False
        self.有顶背离 = False
    
    def _检测顶背离(self):
        """顶背离: 价格在20根内高点附近, 但RSI远低于20根内RSI高点"""
        if len(self.价格历史) < self.前看K线数:
            return False
        
        近20价 = self.价格历史[-self.前看K线数:]
        近20RSI = self.RSI历史[-self.前看K线数:]
        
        当前收盘 = 近20价[-1]
        最高收盘 = max(近20价)
        当前RSI = 近20RSI[-1]
        最高RSI = max(近20RSI)
        
        # 条件1: 价格在近期高点附近(2%以内)
        价格近高点 = 当前收盘 >= 最高收盘 * 0.98
        # 条件2: RSI远低于高点(至少跌10点)
        RSI远低于高点 = 当前RSI <= 最高RSI - 10
        
        return 价格近高点 and RSI远低于高点
    
    def _检测底背离(self):
        """底背离: 价格在20根内低点附近, 但RSI远高于20根内RSI低点"""
        if len(self.价格历史) < self.前看K线数:
            return False
        
        近20价 = self.价格历史[-self.前看K线数:]
        近20RSI = self.RSI历史[-self.前看K线数:]
        
        当前收盘 = 近20价[-1]
        最低收盘 = min(近20价)
        当前RSI = 近20RSI[-1]
        最低RSI = min(近20RSI)
        
        # 条件1: 价格在近期低点附近(2%以内)
        价格近低点 = 当前收盘 <= 最低收盘 * 1.02
        # 条件2: RSI远高于低点(至少涨10点)
        RSI远高于低点 = 当前RSI >= 最低RSI + 10
        
        return 价格近低点 and RSI远高于低点
    
    def 每根K线处理(self, K线数据, 全局状态) -> dict:
        收盘 = K线数据.get('前复权_收盘', 0)
        rsi = K线数据.get('RSI_14', 50)
        if 收盘 > 0:
            self.价格历史.append(收盘); self.RSI历史.append(rsi)
            if len(self.价格历史) > self.前看K线数 * 3:
                self.价格历史.pop(0); self.RSI历史.pop(0)
        self.有顶背离 = self._检测顶背离()
        self.有底背离 = self._检测底背离()
        if 全局状态 is not None:
            全局状态['有顶背离'] = self.有顶背离
            全局状态['有底背离'] = self.有底背离
        return {"顶背离": self.有顶背离, "底背离": self.有底背离}
    
    def 买入前检查(self, K线数据, 全局状态) -> dict:
        if self.有顶背离:
            return {"允许买入": False, "质量分调整": 0.3, "说明": "顶背离拦截"}
        if self.有底背离:
            return {"允许买入": True, "质量分调整": 1.2, "说明": "底背离加强"}
        return {"允许买入": True, "质量分调整": 1.0, "说明": "无背离"}
    
    def 重置(self):
        self.价格历史 = []; self.RSI历史 = []
        self.有底背离 = False; self.有顶背离 = False

if __name__ == "__main__":
    因子 = RSI背离检测({"前看K线数": 20})
    print("RSI背离检测 自检 OK")
    for i in range(30):
        价 = 100 + i if i < 20 else 119 - (i-20) * 0.5
        rsi = 80 - i * 0.5 if i < 15 else 72.5 + (i-15) * 0.3
        因子.每根K线处理({"前复权_收盘": 价, "RSI_14": rsi}, {})
    print(f"  顶背离={因子.有顶背离}, 底背离={因子.有底背离}")
