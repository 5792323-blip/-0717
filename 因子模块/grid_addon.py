#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# grid_addon.py — 网格加仓（独立小程序）
#
# 需求（来自策略0717页面化/积木化）：
# - 开仓后允许最多追加加仓 N 次（不包含首次开仓）
# - 第 i 次加仓触发条件：价格从“上次加仓后最高价”（仅使用上一根已完成状态，避免未来函数）
#   回撤 i*base_drop_pct（例如 5%/10%/15%/...）且卖出条件未触发
# - 加仓模式可选：固定分层、线性递增（1、2、3...）、倍数加仓（1、2、4、8...）
#   或生命周期预算分层（首次25%、L1 15%、L2-L4各20%）。
# - 网格触发与实际成交分离：触发时先累计待加仓数量，待新的买入信号出现后由执行器合并成交。
# - 具体成交与风控由执行器统一处理（现金、总仓位、单股比例等）

from 因子模块.因子基类 import 因子基类


class 网格加仓(因子基类):
    def __init__(self, 参数=None):
        super().__init__(参数)
        self.名称 = "网格加仓"
        self.最大加仓次数 = int(self.参数.get("最大加仓次数", 5))
        self.首次回撤阈值 = float(self.参数.get("首次回撤阈值", 0.05))
        self.允许同根多次加仓 = bool(self.参数.get("允许同根多次加仓", False))
        self.启用风控限制 = bool(self.参数.get("启用风控限制", False))
        self.最小加仓间隔K线 = max(0, int(self.参数.get("最小加仓间隔K线", 5)))
        self.禁止加仓持仓K线数 = max(0, int(self.参数.get("禁止加仓持仓K线数", 30)))
        self.加仓模式 = str(self.参数.get("加仓模式", "multiplier"))
        self.倍数 = max(1.0, float(self.参数.get("倍数", 2.0)))
        比例 = self.参数.get("生命周期预算比例", [0.25, 0.15, 0.20, 0.20, 0.20])
        try:
            self.生命周期预算比例 = [float(value) for value in 比例]
        except (TypeError, ValueError):
            self.生命周期预算比例 = [0.25, 0.15, 0.20, 0.20, 0.20]
        if (len(self.生命周期预算比例) != 5
                or any(value <= 0 for value in self.生命周期预算比例)
                or abs(sum(self.生命周期预算比例) - 1.0) > 1e-6):
            self.生命周期预算比例 = [0.25, 0.15, 0.20, 0.20, 0.20]
        self.生命周期预算金额 = max(
            0.0, float(self.参数.get("生命周期预算金额", 0.0) or 0.0)
        )

    def 加仓前检查(self, 持仓, K线数据, 全局状态) -> dict:
        # 没有持仓或参数异常 → 不触发
        if not 持仓 or self.最大加仓次数 <= 0 or self.首次回撤阈值 <= 0:
            return {"触发加仓": False}

        # “已触发次数”与“已成交次数”分离：网格先触发记账，等买入信号恢复后再成交。
        已触发次数 = int(持仓.get("网格_已触发次数", 持仓.get("网格_已加仓次数", 0)) or 0)
        最大加仓次数 = 4 if self.加仓模式 == "lifecycle_budget" else self.最大加仓次数
        if 已触发次数 >= 最大加仓次数:
            return {"触发加仓": False, "说明": f"已达最大加仓次数{最大加仓次数}"}

        if self.启用风控限制:
            当前索引 = 全局状态.get("当前索引")
            买入时间 = 持仓.get("买入时间")
            最近加仓索引 = 持仓.get("网格_最近加仓索引")
            try:
                当前索引 = int(当前索引)
            except (TypeError, ValueError):
                当前索引 = None
            try:
                买入时间 = int(买入时间)
            except (TypeError, ValueError):
                买入时间 = None
            try:
                最近加仓索引 = int(最近加仓索引)
            except (TypeError, ValueError):
                最近加仓索引 = 买入时间

            if (当前索引 is not None and 最近加仓索引 is not None
                    and 当前索引 - 最近加仓索引 < self.最小加仓间隔K线):
                return {
                    "触发加仓": False,
                    "说明": f"网格风控：距上次成交不足{self.最小加仓间隔K线}根K线",
                }
            if (当前索引 is not None and 买入时间 is not None
                    and 当前索引 - 买入时间 >= self.禁止加仓持仓K线数):
                return {
                    "触发加仓": False,
                    "说明": f"网格风控：持仓已达{self.禁止加仓持仓K线数}根K线，冻结加仓",
                }

        首笔股数 = int(持仓.get("网格_首笔股数", 0) or 0)
        if 首笔股数 <= 0 and self.加仓模式 != "lifecycle_budget":
            return {"触发加仓": False, "说明": "缺少首笔股数，无法网格加仓"}

        # 仅使用“上一根已完成状态”的网格参考高点，避免把本根最高价纳入导致同根未来函数
        基准高点 = 持仓.get("网格_基准最高价")
        try:
            基准高点 = float(基准高点) if 基准高点 is not None else None
        except (TypeError, ValueError):
            基准高点 = None
        if not 基准高点 or 基准高点 <= 0:
            return {"触发加仓": False, "说明": "缺少网格基准高点"}

        本次序号 = 已触发次数 + 1  # 1..最大加仓次数
        本次回撤 = self.首次回撤阈值 * 本次序号
        触发价 = 基准高点 * (1 - 本次回撤)

        # 触发条件：本根最低价跌破触发价
        当前最低 = K线数据.get("前复权_最低", None)
        try:
            当前最低 = float(当前最低) if 当前最低 is not None else None
        except (TypeError, ValueError):
            当前最低 = None
        if 当前最低 is None or 当前最低 <= 0:
            return {"触发加仓": False}

        if 当前最低 > 触发价:
            return {"触发加仓": False}

        if self.加仓模式 == "lifecycle_budget":
            return {
                "触发加仓": True,
                "触发价": float(触发价),
                "加仓金额": float(self.生命周期预算金额 * self.生命周期预算比例[本次序号]),
                "网格层级": 本次序号,
                "网格模式": self.加仓模式,
                "加仓原因": f"生命周期预算网格#{本次序号} 回撤{本次回撤*100:.1f}% 触发",
                "说明": (
                    f"模式={self.加仓模式}, 基准高点={基准高点:.2f}, "
                    f"触发价={触发价:.2f}, 预算={self.生命周期预算金额 * self.生命周期预算比例[本次序号]:.2f}元"
                ),
            }
        if self.加仓模式 == "fixed_tranche":
            目标股数 = 首笔股数
        elif self.加仓模式 == "linear":
            目标股数 = 首笔股数 * (本次序号 + 1)
        else:
            # 首笔开仓为1倍，后续加仓为2、4、8...倍首笔。
            目标股数 = 首笔股数 * (self.倍数 ** 本次序号)
        目标股数 = max(100, int(目标股数 / 100) * 100)

        return {
            "触发加仓": True,
            "触发价": float(触发价),
            "加仓股数": int(目标股数),
            "网格层级": 本次序号,
            "加仓原因": f"网格加仓#{本次序号} 回撤{本次回撤*100:.1f}% 触发",
            "说明": f"模式={self.加仓模式}, 基准高点={基准高点:.2f}, 触发价={触发价:.2f}, 最低={当前最低:.2f}, 买入={目标股数}股",
        }

    def 重置(self):
        pass


if __name__ == "__main__":
    因子 = 网格加仓({"最大加仓次数": 5, "首次回撤阈值": 0.05})
    print("网格加仓 自检 OK")
