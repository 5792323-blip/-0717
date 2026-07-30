#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 因子管理器.py — 统一加载、调度所有因子
#
# 功能:
#   ① 加载因子配置.yaml → 确定哪些因子启用
#   ② 动态导入对应的.py文件 → 实例化
#   ③ 按时机调用: 每根K线 / 买入前 / 卖出前
#
# 用法:
#   管理器 = 因子管理器("1_策略配置/")
#   管理器.买入前检查(K线数据, 全局状态)

import os, sys, yaml, importlib, inspect
from 模块系统 import 模块开关管理器

项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class 因子管理器:
    """统一调度所有因子"""
    
    def __init__(self, 配置目录):
        self.配置目录 = 配置目录
        self.模块开关 = 模块开关管理器(配置目录)
        self.已启用因子 = {}   # {名称: 因子实例}
        self.所有因子 = {}     # {名称: 因子实例} (含已禁用)
        
        # 加载配置
        配置路径 = os.path.join(配置目录, '因子配置.yaml')
        if not os.path.exists(配置路径):
            # 兼容旧版 — 没有配置文件时跳过
            print("[因子管理器] ⚠️ 无因子配置.yaml，跳过因子加载")
            return
        
        with open(配置路径, 'r', encoding='utf-8') as f:
            self.配置 = yaml.safe_load(f)
        
        全局开关 = self.配置.get('全局因子开关', True)
        if not 全局开关:
            print("[因子管理器] 全局因子开关=关，所有因子已禁用")
            return
        
        因子列表 = self.配置.get('因子列表', {})
        模块目录 = os.path.join(项目根目录, '因子模块')
        sys.path.insert(0, 项目根目录)
        
        for 名称, 配置 in 因子列表.items():
            中央标识 = {'波动率分类器': 'volatility_classifier'}.get(名称, 名称)
            启用 = self.模块开关.是否启用('扩展因子', 中央标识, 配置.get('启用', False))
            说明 = 配置.get('说明', '')
            参数 = 配置.get('参数', {})
            
            # 尝试导入对应模块
            实例 = self._加载因子(名称, 参数)
            if 实例:
                实例.名称 = 名称
                实例.说明 = 说明
                self.所有因子[名称] = 实例
                if 启用:
                    self.已启用因子[名称] = 实例
                    print(f"[因子管理器] ✅ {名称} — 已启用")
                else:
                    print(f"[因子管理器] ⏸  {名称} — 已禁用")
        
        print(f"[因子管理器] 已加载 {len(self.已启用因子)}/{len(self.所有因子)} 个因子")
    
    def _加载因子(self, 名称, 参数):
        """动态导入因子模块，返回实例"""
        try:
            # 尝试导入 因子模块.名称
            mod = importlib.import_module(f'因子模块.{名称}')
            # 找类名（通常跟文件名一致或叫class_名称）
            for name, obj in inspect.getmembers(mod, inspect.isclass):
                # 只实例化模块自身定义的因子类；CMSF 等公共基类被 import
                # 进来时不能被误当成具体插件。
                if (name != '因子基类' and obj.__module__ == mod.__name__
                        and issubclass(obj, __import__('因子模块.因子基类', fromlist=['因子基类']).因子基类)):
                    return obj(参数)
            # 如果没有找到子类，试试模块名本身有 计算 函数
            if hasattr(mod, '计算'):
                return mod
        except ModuleNotFoundError:
            pass
        except Exception as e:
            print(f"[因子管理器] ⚠️ 加载 {名称} 失败: {e}")
        return None
    
    def 重置(self):
        """重置所有因子"""
        for 因子 in self.已启用因子.values():
            if hasattr(因子, '重置'):
                因子.重置()
    
    def 每根K线处理(self, K线数据, 全局状态) -> dict:
        """
        每根K线调用所有已启用的因子
        传出: {"因子1_结果": {...}, "因子2_结果": {...}}
        """
        结果 = {}
        for 名称, 因子 in self.已启用因子.items():
            if hasattr(因子, '每根K线处理'):
                try:
                    结果[名称] = 因子.每根K线处理(K线数据, 全局状态)
                except Exception as e:
                    结果[名称] = {"错误": str(e)}
        return 结果
    
    def 买入前检查(self, K线数据, 全局状态) -> dict:
        """
        检查是否允许买入
        所有因子都返回"允许买入"=True 才允许
        质量分调整 = 所有因子的乘积
        
        传出: {
            "允许买入": True/False,
            "质量分调整": 0.0~1.0,
            "说明": [因子1说明, 因子2说明],
            "明细": {因子名称: 结果}
        }
        """
        允许买入 = True
        质量分调整 = 1.0
        建议仓位列表 = []
        说明列表 = []
        明细 = {}
        
        for 名称, 因子 in self.已启用因子.items():
            if hasattr(因子, '买入前检查'):
                try:
                    检查结果 = 因子.买入前检查(K线数据, 全局状态)
                    明细[名称] = 检查结果
                    if not 检查结果.get("允许买入", True):
                        允许买入 = False
                        说明列表.append(f"{名称}: 拦截({检查结果.get('说明','')})")
                    质量分调整 *= 检查结果.get("质量分调整", 1.0)
                    if 检查结果.get("建议仓位") is not None:
                        建议仓位列表.append(float(检查结果["建议仓位"]))
                except Exception as e:
                    明细[名称] = {"错误": str(e)}
                    允许买入 = False
                    说明列表.append(f"{名称}: 异常拦截({e})")
        
        return {
            "允许买入": 允许买入,
            "质量分调整": max(0.0, min(质量分调整, 1.0)),
            # 多个仓位模块同时启用时采用最保守值，避免叠加后突破风控上限。
            "建议仓位": min(建议仓位列表) if 建议仓位列表 else None,
            "说明": " | ".join(说明列表),
            "明细": 明细,
        }
    
    def 卖出前检查(self, 持仓, K线数据, 全局状态) -> list:
        """
        检查是否触发卖出
        任意因子返回"触发卖出"=True 即触发
        
        传出: [{"触发卖出": True, "触发价": ..., "卖出原因": ..., "因子": 名称}, ...]
        """
        触发列表 = []
        
        for 名称, 因子 in self.已启用因子.items():
            if hasattr(因子, '卖出前检查'):
                try:
                    检查结果 = 因子.卖出前检查(持仓, K线数据, 全局状态)
                    if 检查结果.get("触发卖出", False):
                        检查结果["因子"] = 名称
                        触发列表.append(检查结果)
                except Exception as e:
                    pass
        
        return 触发列表

    def 卖出信号过滤(self, 持仓, K线数据, 全局状态, 卖出规则) -> dict:
        """仅对既有卖出规则做可选放行/拦截，不产生新的卖出订单。"""
        allowed = True
        details = {}
        reasons = []
        for 名称, 因子 in self.已启用因子.items():
            if not hasattr(因子, '卖出信号过滤'):
                continue
            try:
                item = 因子.卖出信号过滤(持仓, K线数据, 全局状态, 卖出规则)
                details[名称] = item
                if not item.get('允许卖出', True):
                    allowed = False
                    reasons.append(f"{名称}: {item.get('说明', '未放行')}")
            except Exception as error:
                # 过滤器异常时保持原卖出规则，不让观察模块扩大交易风险。
                details[名称] = {'错误': str(error)}
        return {'允许卖出': allowed, '说明': ' | '.join(reasons), '明细': details}

    def 加仓前检查(self, 持仓, K线数据, 全局状态) -> list:
        """
        检查是否触发加仓（已有持仓情况下的增持/网格加仓）

        触发规则:
            - 任意因子返回"触发加仓"=True 即视为触发

        传出:
            [{"触发加仓": True, "触发价": ..., "加仓股数": ..., "加仓原因": ..., "因子": 名称}, ...]
        """
        触发列表 = []
        for 名称, 因子 in self.已启用因子.items():
            if hasattr(因子, '加仓前检查'):
                try:
                    检查结果 = 因子.加仓前检查(持仓, K线数据, 全局状态)
                    if 检查结果.get("触发加仓", False):
                        检查结果["因子"] = 名称
                        触发列表.append(检查结果)
                except Exception:
                    pass
        return 触发列表
    
    def 获取结果(self) -> dict:
        """获取所有因子的统计结果"""
        统计 = {"已启用": len(self.已启用因子), "总数": len(self.所有因子)}
        for 名称, 因子 in self.已启用因子.items():
            if hasattr(因子, '获取统计'):
                统计[名称] = 因子.获取统计()
        return 统计
    
    def __repr__(self):
        return f"<因子管理器: {len(self.已启用因子)}/{len(self.所有因子)} 启用>"


if __name__ == "__main__":
    # 自检
    print("=" * 50)
    print("因子管理器 自检")
    print("=" * 50)
    
    配置目录 = os.path.join(项目根目录, '1_策略配置')
    管理器 = 因子管理器(配置目录)
    管理器.重置()
    
    模拟K线 = {"前复权_收盘": 1000, "RSI_14": 25, "RSI_均线_20": 30}
    模拟状态 = {"大盘状态": "震荡模式", "当前持仓": {}}
    
    买入结果 = 管理器.买入前检查(模拟K线, 模拟状态)
    print(f"\n买入前检查: {买入结果}")
    
    统计 = 管理器.获取结果()
    print(f"\n统计: {统计}")
    print("\n✅ 自检完成")
