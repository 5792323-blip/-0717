#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ma_direction.py — MA方向过滤 (独立小程序)
# 规则: MA斜率<-阈值拦截追跌 / MA斜率>+阈值拦截追涨
#
# 支持动态阈值：
#   如果全局状态中有"波动率分类" → 使用其建议的下跌/上涨拦截阈值
#   否则 → 使用配置文件中的固定阈值

from 因子模块.因子基类 import 因子基类

class MA方向过滤(因子基类):
    def __init__(self, 参数=None):
        super().__init__(参数)
        self.名称 = "MA方向过滤"
        self.MA历史 = []
        # 固定阈值（兜底）
        self.下跌阈值 = self.参数.get('下跌拦截阈值', -1.5)
        self.上涨阈值 = self.参数.get('上涨拦截阈值', 1.5)
    
    def 每根K线处理(self, K线数据, 全局状态) -> dict:
        ma = K线数据.get('RSI_均线_20', None)
        if ma and not (isinstance(ma, float) and str(ma) == 'nan'):
            self.MA历史.append(ma)
            if len(self.MA历史) > 20:
                self.MA历史.pop(0)
        return {"MA": ma}
    
    def _斜率(self):
        return self.MA历史[-1] - self.MA历史[-6] if len(self.MA历史) >= 6 else 0.0
    
    def _获取有效阈值(self, 全局状态):
        """
        从全局状态读取动态阈值（由波动率分类器提供）
        如果没有，使用固定阈值
        """
        波动分类 = 全局状态.get("波动率分类", {}) if 全局状态 else {}
        if 波动分类 and 波动分类.get("建议_下跌拦截") is not None:
            跌 = 波动分类["建议_下跌拦截"]
            涨 = 波动分类["建议_上涨拦截"]
            return 跌, 涨, f"动态(波动率{波动分类.get('波动率','?')}%/{波动分类.get('分类','?')})"
        return self.下跌阈值, self.上涨阈值, "固定"
    
    def 买入前检查(self, K线数据, 全局状态) -> dict:
        下跌阈值, 上涨阈值, 来源 = self._获取有效阈值(全局状态)
        斜率 = self._斜率()
        
        if 斜率 < 下跌阈值:
            return {
                "允许买入": False, "质量分调整": 0.3,
                "说明": f"MA大跌斜率={斜率:.1f}<-{下跌阈值:.1f}[{来源}]"
            }
        if 斜率 > 上涨阈值:
            return {
                "允许买入": False, "质量分调整": 0.4,
                "说明": f"MA大涨斜率={斜率:.1f}>{上涨阈值:.1f}[{来源}]"
            }
        if 斜率 < 0:
            return {
                "允许买入": True, "质量分调整": 0.7,
                "说明": f"MA微跌斜率={斜率:.1f}[{来源}]"
            }
        return {
            "允许买入": True, "质量分调整": 1.0,
            "说明": f"MA上升斜率={斜率:.1f}[{来源}]"
        }
    
    def 重置(self):
        self.MA历史 = []

if __name__ == "__main__":
    因子 = MA方向过滤()
    print("MA方向过滤 自检 OK")
    for i in range(10):
        因子.每根K线处理({"RSI_均线_20": 30 - i * 2.5}, {})
    斜率 = 因子._斜率()
    # 测试固定阈值
    r = 因子.买入前检查({}, {})
    print(f"  固定: 斜率={斜率:.1f}, 拦截={r['允许买入']} ({r['说明']})")
    # 测试动态阈值（模拟波动率分类器结果）
    r2 = 因子.买入前检查({}, {"波动率分类": {"分类": "高波动", "波动率": 22.5, "建议_下跌拦截": -1.0, "建议_上涨拦截": 1.0}})
    print(f"  动态: 斜率={斜率:.1f}, 拦截={r2['允许买入']} ({r2['说明']})")
    print("\n✅ 自检完成")
