#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# take_profit.py — 分批止盈 (独立小程序)
# 盈利5%卖1/3, 10%卖1/3, 20%全清

from 因子模块.因子基类 import 因子基类

class 分批止盈(因子基类):
    def __init__(self, 参数=None):
        super().__init__(参数)
        self.名称 = "分批止盈"
        self.档位 = [
            (self.参数.get('第一档', 0.05), self.参数.get('第一档比例', 1/3)),
            (self.参数.get('第二档', 0.10), self.参数.get('第二档比例', 1/3)),
            (self.参数.get('第三档', 0.20), self.参数.get('第三档比例', 1.0)),
        ]
        self.已触发档位 = set()
    
    def 卖出前检查(self, 持仓, K线数据, 全局状态) -> dict:
        买入价 = 持仓.get('买入价', 0)
        if 买入价 <= 0: return {"触发卖出": False}
        
        当前价 = K线数据.get('不复权_收盘', 0)
        if 当前价 <= 0: return {"触发卖出": False}
        
        盈亏比例 = (当前价 - 买入价) / 买入价
        
        for i, (阈值, 比例) in enumerate(self.档位):
            if 盈亏比例 >= 阈值 and i not in self.已触发档位:
                self.已触发档位.add(i)
                卖出股数 = int(持仓.get('股数', 0) * 比例)
                if 卖出股数 >= 100:
                    return {
                        "触发卖出": True,
                        "触发价": 当前价,
                        "卖出原因": f"分批止盈({阈值*100:.0f}%)",
                        "卖出股数": (卖出股数 // 100) * 100,
                        "说明": f"盈利{盈亏比例*100:.1f}%→触发{阈值*100:.0f}%档"
                    }
        
        return {"触发卖出": False}
    
    def 重置(self): self.已触发档位 = set()

if __name__ == "__main__":
    因子 = 分批止盈()
    print("分批止盈 自检 OK")
    模拟持仓 = {"买入价": 100, "股数": 300}
    for 价 in [102, 106, 108, 112, 105, 125]:
        r = 因子.卖出前检查(模拟持仓, {"不复权_收盘": 价}, {})
        if r['触发卖出']: print(f"  价={价}: 触发={r['卖出原因']}, 股数={r.get('卖出股数','全部')}")
        else: print(f"  价={价}: 未触发")
    print("✅ take_profit 自检完成")
