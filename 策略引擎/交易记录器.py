# 交易记录器.py — 记录每根K线的持仓状态
# 功能: 记录交易过程中所有关键价格和状态
# 用途: 生成K线回放报告时使用，让你在图上看到所有中间过程
#
# 每根K线记录:
#   - 当前价格 (前复权+不复权)
#   - 当前RSI / RSI_MA / ATR
#   - 当前持仓状态
#   - 站岗价 / ATR缓冲价 (如果有)
#   - 哨兵价 (如果有)
#   - 买卖点标记

import pandas as pd
import numpy as np
import json
from datetime import datetime


def 规范化成交时间(时间=None, 日期=None):
    """校验成交时间，并在写入边界将仅有日期的输入规范为时间。"""
    时间缺失 = 时间 is None or 时间 == "" or pd.isna(时间)
    日期缺失 = 日期 is None or 日期 == "" or pd.isna(日期)
    if not 时间缺失:
        时间值 = str(时间).strip()
        时间戳 = pd.to_datetime(时间值, errors="coerce")
        if pd.isna(时间戳):
            raise ValueError("成交时间无效")
        if not 日期缺失:
            日期戳 = pd.to_datetime(日期, errors="coerce")
            if pd.isna(日期戳):
                raise ValueError("成交时间或日期无效")
            if 时间戳.date() != 日期戳.date():
                raise ValueError("成交时间与日期冲突")
        return 时间值
    if 日期缺失:
        raise ValueError("成交时间无效")
    日期值 = str(日期).strip()
    if pd.isna(pd.to_datetime(日期值, errors="coerce")):
        raise ValueError("成交时间或日期无效")
    return 日期值


class 交易记录器:
    """
    交易记录器 — 记录整个交易过程
    
    用法:
        记录器 = 交易记录器()
        记录器.记录本根K线(数据)
        记录器.记录买入(...)
        记录器.记录卖出(...)
        记录器.导出明细()
    """
    
    def __init__(self):
        当前时间 = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.交易列表 = []
        self.持仓记录 = []
        self.买入序号 = 0
        self.持仓组序号 = 0
        self.意图序号 = 0
        self.订单序号 = 0
        self.成交序号 = 0
        self._execution_scope = None
        
        # 当前交易的临时标记
        self.当前哨兵价 = None
        self.当前站岗价 = None
        self.当前ATR缓冲价 = None
        self.当前RSI峰值 = None
        self.当前买入价 = None
        self.当前买入时间 = None
        self.当前信号类型 = None
        self.反推哨兵价列表 = []
        self.信号K线_开盘 = None
        self.信号K线_收盘 = None
        self.信号K线_最高 = None
        self.信号K线_最低 = None

    def 绑定成交作用域(self, scope):
        if self._execution_scope is not None and self._execution_scope is not scope:
            raise ValueError("交易记录器已绑定其他 execution scope")
        self._execution_scope = scope
        scope.setdefault("recorders", set()).add(self)

    def 预留成交ID(self):
        """在账户状态变化前预留当前作用域内唯一的成交 ID。"""
        if self._execution_scope is None:
            self._execution_scope = {
                "execution_ids": set(), "pending_execution_ids": {},
                "committed_execution_ids": set(), "recorders": {self},
            }
        scope = self._execution_scope
        candidate_number = self.成交序号 + 1
        candidate = f"X{candidate_number:08d}"
        if candidate in scope["execution_ids"]:
            raise ValueError(f"重复 execution_id: {candidate}")
        scope["execution_ids"].add(candidate)
        scope.setdefault("pending_execution_ids", {})[candidate] = (self, self.成交序号)
        self.成交序号 = candidate_number
        for recorder in scope["recorders"]:
            if recorder is not self:
                recorder.成交序号 = max(recorder.成交序号, candidate_number)
        return candidate

    def 使用预留成交ID(self, execution_id):
        scope = self._execution_scope
        pending = scope and scope.setdefault("pending_execution_ids", {})
        if not scope or execution_id not in pending or pending[execution_id][0] is not self:
            raise ValueError(f"execution_id 未预留或已提交: {execution_id}")

    def 提交成交ID(self, execution_id):
        scope = self._execution_scope
        pending = scope and scope.setdefault("pending_execution_ids", {})
        if not scope or execution_id not in pending or pending[execution_id][0] is not self:
            raise ValueError(f"execution_id 未预留或已提交: {execution_id}")
        pending.pop(execution_id)
        scope.setdefault("committed_execution_ids", set()).add(execution_id)

    def 释放成交ID(self, execution_id):
        scope = self._execution_scope
        pending = scope and scope.setdefault("pending_execution_ids", {})
        if not scope or execution_id not in pending:
            return
        recorder, previous_sequence = pending.pop(execution_id)
        scope["execution_ids"].discard(execution_id)
        recorder.成交序号 = previous_sequence
    
    def 记录本根K线(self, K线索引, 日期, 时间, 前复权收盘, 不复权收盘, 
                   RSI值, RSI_MA值, ATR值):
        """
        记录每根K线的状态（用于K线回放）
        """
        self.持仓记录.append({
            "K线索引": K线索引,
            "日期": 日期,
            "时间": 时间,
            "前复权收盘": 前复权收盘,
            "不复权收盘": 不复权收盘,
            "RSI": RSI值,
            "RSI_MA": RSI_MA值,
            "ATR": ATR值,
            "哨兵价": self.当前哨兵价,
            "站岗价": self.当前站岗价,
            "ATR缓冲价": self.当前ATR缓冲价,
            "RSI峰值": self.当前RSI峰值,
            "反推哨兵价列表": json.dumps(self.反推哨兵价列表, ensure_ascii=False),
            "过滤检查": "[]",
        })

    def 更新本根K线(self, **字段):
        """补写本根K线的真实策略判断和账户状态。"""
        if not self.持仓记录:
            return
        for key, value in 字段.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, default=str)
            self.持仓记录[-1][key] = value
    
    def 记录信号K线(self, 开盘, 收盘, 最高, 最低):
        """记录产生买入信号的K线数据"""
        self.信号K线_开盘 = 开盘
        self.信号K线_收盘 = 收盘
        self.信号K线_最高 = 最高
        self.信号K线_最低 = 最低
    
    def 设置哨兵价(self, 哨兵价):
        """设置买入哨兵价"""
        self.当前哨兵价 = 哨兵价
    
    def 记录买入(self, 买入价, 信号类型, 信号质量分, 仓位, 
               哨兵价, 哨兵价触发价, 前复权买入价=None, 前复权成交价=None, 日期='', 时间='',
               成交数量=None, 交易费用=None, 总成本=None, 持仓组ID=None,
               网格级别=0, 加仓后总持仓=None, execution_id=None, approval_id=None):
        """记录一笔买入"""
        成交时间 = 规范化成交时间(时间, 日期)
        if execution_id is not None:
            self.使用预留成交ID(execution_id)
        self.买入序号 += 1
        self.意图序号 += 1
        self.订单序号 += 1
        if execution_id is None:
            execution_id = self.预留成交ID()
        if 持仓组ID is None:
            self.持仓组序号 += 1
            持仓组ID = f"G{self.持仓组序号:06d}"
        self.当前买入价 = 买入价
        self.当前信号类型 = 信号类型
        self.当前RSI峰值 = None  # 重置峰值
        self.当前站岗价 = None
        
        买入记录 = {
            "intent_id": f"I{self.意图序号:08d}",
            "order_id": f"O{self.订单序号:08d}",
            "execution_id": execution_id,
            "approval_id": approval_id,
            "rejection_id": None,
            "序号": self.买入序号,
            "持仓组ID": 持仓组ID,
            "网格级别": int(网格级别 or 0),
            "时间": 成交时间,
            "类型": "买入",
            "买入价": 买入价,
            "信号类型": 信号类型,
            "信号质量分": 信号质量分,
            "仓位": 仓位,
            "成交数量": 成交数量,
            "交易费用": 交易费用,
            "总成本": 总成本,
            "加仓后总持仓": 加仓后总持仓,
            "哨兵价": 哨兵价,
            "触发价": 哨兵价触发价,
            "前复权买入价": 前复权买入价,
            "前复权成交价": 前复权成交价,
            "信号K线_开盘": self.信号K线_开盘,
            "信号K线_收盘": self.信号K线_收盘,
            "信号K线_最高": self.信号K线_最高,
            "信号K线_最低": self.信号K线_最低,
        }
        self.交易列表.append(买入记录)
        self.提交成交ID(execution_id)
        
        # 记录到持仓记录
        self.持仓记录[-1]["买入序号"] = self.买入序号
        self.持仓记录[-1]["持仓组ID"] = 持仓组ID
        self.持仓记录[-1]["买入价"] = 买入价
    
    def 更新RSI峰值(self, 当前RSI):
        """跟踪RSI的最高值（用于动能衰竭判断）"""
        if self.当前RSI峰值 is None or 当前RSI > self.当前RSI峰值:
            self.当前RSI峰值 = 当前RSI
    
    def 设置站岗价(self, 站岗价, ATR值, 缓冲倍数=0.5):
        """设置RSI站岗价和ATR缓冲价"""
        self.当前站岗价 = 站岗价
        self.当前ATR缓冲价 = 站岗价 - 缓冲倍数 * ATR值
    
    def 记录反推价突破(self, 价格, 目标RSI, 关卡名):
        """记录一个被价格突破的反推价关卡"""
        for r in self.反推哨兵价列表:
            if abs(r["价格"] - 价格) < 0.01:
                return
        self.反推哨兵价列表.append({
            "价格": 价格,
            "目标RSI": 目标RSI,
            "关卡名": 关卡名,
        })

    def 记录卖出(self, 卖出价, 卖出原因, 盈亏比例, 持有K线数,
               站岗价=None, ATR缓冲价=None, RSI峰值=None, 日期='', 时间='',
               仓位=None, 成交数量=None, 持仓组ID=None, execution_id=None, approval_id=None):
        """记录一笔卖出"""
        成交时间 = 规范化成交时间(时间, 日期)
        if execution_id is not None:
            self.使用预留成交ID(execution_id)
        self.意图序号 += 1
        self.订单序号 += 1
        if execution_id is None:
            execution_id = self.预留成交ID()
        卖出记录 = {
            "intent_id": f"I{self.意图序号:08d}",
            "order_id": f"O{self.订单序号:08d}",
            "execution_id": execution_id,
            "approval_id": approval_id,
            "rejection_id": None,
            "序号": self.买入序号,
            "持仓组ID": 持仓组ID,
            "时间": 成交时间,
            "类型": "卖出",
            "卖出价": 卖出价,
            "卖出原因": 卖出原因,
            "盈亏比例": 盈亏比例,
            "持有K线数": 持有K线数,
            "站岗价": 站岗价 or self.当前站岗价,
            "ATR缓冲价": ATR缓冲价 or self.当前ATR缓冲价,
            "RSI峰值": RSI峰值 or self.当前RSI峰值,
            "仓位": 仓位,
            "成交数量": 成交数量,
        }
        self.交易列表.append(卖出记录)
        self.提交成交ID(execution_id)
        
        # 更新对应的买入记录（填入卖出价和盈亏）
        for 记录 in self.交易列表:
            if (记录.get('类型') == '买入' and
                ((持仓组ID is not None and 记录.get('持仓组ID') == 持仓组ID) or
                 (持仓组ID is None and 记录.get('序号') == 卖出记录['序号']))):
                记录['卖出价'] = 卖出价
                记录['卖出时间'] = 卖出记录['时间']
                记录['卖出原因'] = 卖出原因
                记录['盈亏比例'] = 盈亏比例
                记录['持有K线数'] = 持有K线数
                记录['站岗价'] = 站岗价 or self.当前站岗价
                记录['ATR缓冲价'] = ATR缓冲价 or self.当前ATR缓冲价
                记录['RSI峰值'] = RSI峰值 or self.当前RSI峰值
        
        self.当前哨兵价 = None
        self.当前站岗价 = None
        self.当前ATR缓冲价 = None
        self.当前RSI峰值 = None
        self.当前买入价 = None
        self.当前买入时间 = None
        self.当前信号类型 = None

    def 更新交易记录(self, 序号, 类型, **字段):
        """补写买入或卖出记录的决策快照和成交字段。"""
        for 记录 in reversed(self.交易列表):
            if 记录.get('序号') == 序号 and 记录.get('类型') == 类型:
                for key, value in 字段.items():
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value, ensure_ascii=False, default=str)
                    记录[key] = value
                return
    
    def 导出明细(self):
        """
        导出完整交易明细
        
        传出:
            pandas DataFrame，包含所有买卖记录
        """
        return pd.DataFrame(self.交易列表)
    
    def 导出持仓过程(self):
        """
        导出完整的持仓过程数据
        
        传出:
            pandas DataFrame，包含每根K线的状态
        """
        return pd.DataFrame(self.持仓记录)


if __name__ == "__main__":
    # 自检测试
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    print("=" * 40)
    print("交易记录器 — 自检测试")
    print("=" * 40)
    
    from 数据模块.股票加载器 import 加载股票
    
    数据 = 加载股票("600519", "双价格合并").head(30)
    
    记录器 = 交易记录器()
    
    # 模拟一段交易过程
    for i in range(len(数据)):
        行 = 数据.iloc[i]
        
        记录器.记录本根K线(
            K线索引=i, 日期=行['日期'], 时间=str(行.name.time()),
            前复权收盘=行['前复权_收盘'], 不复权收盘=行['不复权_收盘'],
            RSI值=行['RSI_14'], RSI_MA值=行['RSI_均线_20'], ATR值=行['ATR_14']
        )
        
        # 第5根K线模拟买入
        if i == 5:
            记录器.记录买入(
                买入价=行['不复权_收盘'], 信号类型="RSI上穿20",
                信号质量分=0.85, 仓位=200000,
                哨兵价=行['前复权_收盘'], 哨兵价触发价=行['前复权_收盘']*1.001
            )
        
        # 每次更新RSI峰值
        记录器.更新RSI峰值(行['RSI_14'])
        
        # 第15根K线模拟设置站岗价
        if i == 15:
            记录器.设置站岗价(行['前复权_收盘']*0.98, 行['ATR_14'], 0.5)
        
        # 第25根K线模拟卖出
        if i == 25:
            记录器.记录卖出(
                卖出价=行['不复权_收盘'], 卖出原因="分批止盈(赚5%)",
                盈亏比例=0.052, 持有K线数=20
            )
    
    过程 = 记录器.导出持仓过程()
    print(f"\n持仓记录: {len(过程)} 根K线")
    print(f"交易记录: {len(记录器.交易列表)} 笔")
    print(f"每K线记录列: {list(过程.columns)}")
    print(f"\n前3行:")
    print(过程[['日期','时间','前复权收盘','RSI','哨兵价','站岗价']].head(3))
    print(f"\n买卖点:")
    print(记录器.导出明细()[['类型','信号类型','买入价','卖出价','盈亏比例']])
    
    print("\n✅ 交易记录器自检完成")
