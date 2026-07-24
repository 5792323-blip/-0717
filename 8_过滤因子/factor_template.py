#!/usr/bin/env python3
"""过滤因子统一模板。"""

from abc import ABC, abstractmethod


class FactorTemplate(ABC):
    名称 = "未命名过滤因子"

    def __init__(self, 配置=None):
        self.配置 = 配置 or {}

    @abstractmethod
    def 检查(self, 哨兵价类型, K线数据, 状态):
        """返回 {通过: bool, 原因: str}。"""
        raise NotImplementedError
