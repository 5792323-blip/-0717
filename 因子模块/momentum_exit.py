#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# momentum_exit.py — 动能衰竭退出 (独立小程序)
# 当RSI从持仓期间的最高值回落到阈值时触发卖出
# 类似站岗价逻辑：RSI峰值-回落值=目标RSI，算反推价作为触发价

from 因子模块.因子基类 import 因子基类

class 动能衰竭退出(因子基类):
    def __init__(self, 参数=None):
        super().__init__(参数)
        self.名称 = "动能衰竭退出"
        self.RSI回落阈值 = self.参数.get('RSI回落阈值', 15)
    
    def 卖出前检查(self, 持仓, K线数据, 全局状态) -> dict:
        """
        检查RSI是否从峰值回落到阈值
        持仓传入: {"买入价": float, "RSI峰值": float, "股数": int, ...}
        """
        当前RSI = K线数据.get('RSI_14', 50)
        RSI峰值 = 持仓.get('RSI峰值', 当前RSI)
        
        # 更新峰值
        if 当前RSI > RSI峰值:
            持仓['RSI峰值'] = 当前RSI
            return {"触发卖出": False, "触发价": None, "卖出原因": "", "说明": f"RSI新高{当前RSI:.1f}"}
        
        回落幅度 = RSI峰值 - 当前RSI
        if 回落幅度 >= self.RSI回落阈值:
            # 尝试用反推公式计算触发价
            触发价 = 持仓.get('买入价') * (1 - 0.02)  # 简版：买入价下方2%
            return {"触发卖出": True, "触发价": 触发价, "卖出原因": f"动能衰竭(RSI回落{回落幅度:.1f})", "说明": f"RSI从{RSI峰值:.1f}跌到{当前RSI:.1f}"}
        
        return {"触发卖出": False, "触发价": None, "卖出原因": "", "说明": f"RSI回落{回落幅度:.1f}(未达{self.RSI回落阈值})"}
    
    def 重置(self): pass

if __name__ == "__main__":
    因子 = 动能衰竭退出({"RSI回落阈值": 15})
    print("动能衰竭退出 自检 OK")
    持仓 = {"买入价": 100, "RSI峰值": 50, "股数": 100}
    # 模拟下跌
    for i in range(5):
        r = 因子.卖出前检查(持仓, {"RSI_14": 50 - i * 5}, {})
        print(f"  RSI={50-i*5:.0f}: 触发={r['触发卖出']}, 说明={r['说明']}")
