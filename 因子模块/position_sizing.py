#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# position_sizing.py — 半凯利仓位管理（独立小程序）
#
# 每个 RSI 信号使用独立的胜率和盈亏比；最终仓位还要经过波动率、
# 单股上限、总仓位上限和现金底线约束。默认关闭。

import math

from 因子模块.因子基类 import 因子基类


默认信号 = ("RSI上穿20", "RSI上穿30", "RSI上穿均线", "RSI上穿70")


class 凯利仓位管理(因子基类):
    def __init__(self, 参数=None):
        super().__init__(参数)
        self.名称 = "凯利仓位管理"
        self.半凯利系数 = float(self.参数.get("凯利折扣", 0.5))
        self.最小样本数 = int(self.参数.get("最小样本数", 30))
        self.单股上限比例 = float(self.参数.get("单股上限比例", 0.10))
        self.总仓位上限比例 = float(self.参数.get("总仓位上限比例", 0.98))
        self.现金底线比例 = float(self.参数.get("现金底线比例", 0.20))
        self.目标年化波动率 = float(self.参数.get("目标年化波动率", 0.20))
        self.高波动阈值 = float(self.参数.get("高波动阈值", 0.40))
        self.高波动折扣 = float(self.参数.get("高波动折扣", 0.70))
        self.低波动阈值 = float(self.参数.get("低波动阈值", 0.20))
        self.低波动加成 = float(self.参数.get("低波动加成", 1.00))
        self.信号统计 = self._读取信号统计()

    def _读取信号统计(self):
        raw = self.参数.get("信号统计", {}) or {}
        result = {}
        for signal in 默认信号:
            item = raw.get(signal, {}) or {}
            result[signal] = {
                "胜率": float(item.get("胜率", 0.0) or 0.0),
                "平均盈利": float(item.get("平均盈利", 0.0) or 0.0),
                "平均亏损": abs(float(item.get("平均亏损", 0.0) or 0.0)),
                "样本数": int(item.get("样本数", 0) or 0),
            }
        return result

    @staticmethod
    def _有限值(value, default=0.0):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return default
        return value if math.isfinite(value) else default

    def _波动率调整(self, K线数据):
        close = self._有限值(K线数据.get("前复权_收盘", K线数据.get("收盘价")))
        atr = self._有限值(K线数据.get("ATR_14"))
        if close <= 0 or atr <= 0:
            return 1.0, None
        年化波动率 = atr / close * math.sqrt(252)
        if 年化波动率 >= self.高波动阈值:
            return self.高波动折扣, 年化波动率
        if 年化波动率 <= self.低波动阈值:
            return self.低波动加成, 年化波动率
        return min(1.0, self.目标年化波动率 / 年化波动率), 年化波动率

    def 买入前检查(self, K线数据, 全局状态) -> dict:
        state = 全局状态 or {}
        signal = state.get("信号类型", K线数据.get("信号类型", ""))
        stats = self.信号统计.get(signal)
        if not stats:
            return {"允许买入": False, "建议仓位": 0, "说明": f"凯利未配置{signal}统计"}

        p = stats["胜率"]
        loss = stats["平均亏损"]
        win = stats["平均盈利"]
        sample = stats["样本数"]
        if sample < self.最小样本数 or loss <= 0 or win <= 0 or not 0 < p < 1:
            return {
                "允许买入": False,
                "建议仓位": 0,
                "说明": f"凯利统计不足/无效: {signal} 样本{sample}，需{self.最小样本数}",
            }

        b = win / loss
        q = 1.0 - p
        full_kelly = (b * p - q) / b
        half_kelly = max(0.0, min(full_kelly * self.半凯利系数, self.单股上限比例))
        vol_adjust, annual_vol = self._波动率调整(K线数据)
        target_fraction = half_kelly * vol_adjust

        equity = self._有限值(state.get("总权益"))
        if equity <= 0:
            return {"允许买入": False, "建议仓位": 0, "说明": "凯利缺少有效总权益"}

        current_position_value = self._有限值(state.get("当前持仓市值", 0.0))
        current_total_fraction = current_position_value / equity
        remaining_total = max(0.0, self.总仓位上限比例 - current_total_fraction)
        remaining_cash = max(0.0, self._有限值(state.get("当前现金", 0.0)) - equity * self.现金底线比例)
        amount = min(equity * target_fraction, equity * self.单股上限比例,
                     equity * remaining_total, remaining_cash)
        if amount <= 0:
            return {"允许买入": False, "建议仓位": 0, "说明": "凯利受组合仓位或现金底线拦截"}

        vol_text = "未知" if annual_vol is None else f"年化波动{annual_vol:.1%}"
        return {
            "允许买入": True,
            "建议仓位": amount,
            "凯利比例": half_kelly,
            "波动率调整": vol_adjust,
            "胜率": p,
            "盈亏比": b,
            "样本数": sample,
            "说明": f"{signal}: 半凯利{half_kelly:.2%}×波动{vol_adjust:.2f}→{amount:.0f}元（{vol_text}）",
        }

    def 重置(self):
        pass
