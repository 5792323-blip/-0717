#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# rsi_ma_filter.py — RSI_MA假信号过滤 (独立小程序)
# 规则: 当前MA > 前N根MA最高值 → 拦截（防止单根阳线拉高MA）

from 因子模块.因子基类 import 因子基类

class RSI_MA假信号过滤(因子基类):
    def __init__(self, 参数=None):
        super().__init__(参数)
        self.名称 = "RSI_MA假信号过滤"
        self.MA历史 = []
        self.前看K线数 = self.参数.get('前看K线数', 5)
    
    def 每根K线处理(self, K线数据, 全局状态) -> dict:
        ma = K线数据.get('RSI_均线_20', None)
        if ma and not (isinstance(ma, float) and str(ma) == 'nan'):
            self.MA历史.append(ma)
            if len(self.MA历史) > self.前看K线数 * 3: self.MA历史.pop(0)
        return {"MA": ma}
    
    def 买入前检查(self, K线数据, 全局状态) -> dict:
        信号类型 = 全局状态.get('哨兵价形成类型', '') if 全局状态 else ''
        if '均线' not in 信号类型:
            return {"允许买入": True, "质量分调整": 1.0, "说明": "非均线信号"}
        if len(self.MA历史) < self.前看K线数 + 1:
            return {"允许买入": True, "质量分调整": 1.0, "说明": "历史不足"}
        当前MA = self.MA历史[-1]
        前N根最高 = max(self.MA历史[-(self.前看K线数+1):-1])
        if 当前MA > 前N根最高:
            return {"允许买入": False, "质量分调整": 0.5, "说明": f"MA突破前高({前N根最高:.1f})→拦截"}
        return {"允许买入": True, "质量分调整": 1.0, "说明": f"MA未破前高({前N根最高:.1f})"}
    
    def 重置(self): self.MA历史 = []

if __name__ == "__main__":
    因子 = RSI_MA假信号过滤()
    print("RSI_MA假信号过滤 自检 OK")
    for i in range(10):
        因子.每根K线处理({"RSI_均线_20": 25 + i * 2}, {})
    print(f"  拦截={因子.买入前检查({}, {'哨兵价形成类型': 'RSI上穿均线'})}")
