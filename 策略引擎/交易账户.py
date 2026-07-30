"""交易账户状态与组合资金审批。

策略执行器负责信号、价格、请求股数、费用和网格状态；账户只保存真实
现金/持仓，并按主页仓位参数给出可用资金。单股账户和多股共享账户使用
同一实现，差别仅在是否被多个股票视图共同引用。
"""

from collections import defaultdict
from collections.abc import MutableMapping

from 数据模块.股票名称 import 获取股票名称


def _规范股票代码(value):
    code = str(value or "").strip().upper()
    for prefix in ("SH_", "SZ_", "BJ_"):
        if code.startswith(prefix):
            return code[len(prefix):]
    return code


class 股票持仓视图(MutableMapping):
    """只向一个股票执行器暴露该股票的真实持仓。"""

    def __init__(self, account, stock):
        self._account = account
        self._stock = str(stock)

    def _实际键(self):
        target = _规范股票代码(self._stock)
        return next(
            (key for key in self._account.持仓 if _规范股票代码(key) == target),
            None,
        )

    def _检查键(self, key):
        if _规范股票代码(key) != _规范股票代码(self._stock):
            raise KeyError(key)

    def __getitem__(self, key):
        self._检查键(key)
        actual = self._实际键()
        if actual is None:
            raise KeyError(key)
        return self._account.持仓[actual]

    def __setitem__(self, key, value):
        self._检查键(key)
        actual = self._实际键()
        self._account.持仓[actual if actual is not None else str(key)] = value

    def __delitem__(self, key):
        self._检查键(key)
        actual = self._实际键()
        if actual is None:
            raise KeyError(key)
        del self._account.持仓[actual]

    def __iter__(self):
        actual = self._实际键()
        if actual is not None:
            yield actual

    def __len__(self):
        return int(self._实际键() is not None)


class 股票账户视图:
    """共享账户面向单个策略执行器的窄接口。"""

    def __init__(self, account, stock):
        self.账户 = account
        self.股票代码 = str(stock)
        self.持仓 = 股票持仓视图(account, self.股票代码)

    @property
    def 现金(self):
        return self.账户.现金

    @现金.setter
    def 现金(self, value):
        self.账户.现金 = float(value)

    def 更新估值价(self, price):
        try:
            price = float(price)
        except (TypeError, ValueError):
            return
        if price > 0:
            self.账户.最新价格[_规范股票代码(self.股票代码)] = price

    def 已达到最大持仓数(self, max_positions):
        if int(max_positions) <= 0:
            return False
        return (
            len(self.持仓) == 0
            and len(self.账户.持仓) >= int(max_positions)
        )

    def 计算结构性可用金额(
        self, estimate_price, max_single_ratio, max_total_ratio, cash_floor
    ):
        """按原单股公式计算账户可用金额，并返回组合审批证据。

        第一阶段刻意保持原公式：最大单只比例是本次结构性上限，总仓位
        使用当前真实持仓市值扣减。这样账户抽取不会改变已验证单股结果。
        """
        self.更新估值价(estimate_price)
        market_value = self.账户.持仓市值()
        equity = self.账户.现金 + market_value
        cash_available = max(
            0.0, self.账户.现金 - equity * float(cash_floor)
        )
        # 最大单只/总仓位比例设为 0 表示关闭对应限制；账户始终受真实
        # 现金余额约束，不能透支。
        single_limit_enabled = float(max_single_ratio) > 0
        single_limit = equity * float(max_single_ratio) if single_limit_enabled else cash_available
        total_limit_enabled = float(max_total_ratio) > 0
        total_remaining = (
            max(0.0, equity * float(max_total_ratio) - market_value)
            if total_limit_enabled else cash_available
        )
        available = min(single_limit, total_remaining, cash_available)
        limits = {
            "当前权益": equity,
            "持仓市值": market_value,
            "单只结构性上限": single_limit,
            "单只仓位限制已关闭": not single_limit_enabled,
            "总仓位剩余": total_remaining,
            "总仓位限制已关闭": not total_limit_enabled,
            "现金可用金额": cash_available,
        }
        return available, limits

    def 记录审批(self, **row):
        result = str(row.get("结果", ""))
        if result not in {"通过", "已通过", "成交"} and (
            "拒绝" in result or "部分" in result or row.get("原因")
        ):
            self.账户.拒绝序号 += 1
            row.setdefault("rejection_id", f"R{self.账户.拒绝序号:08d}")
        else:
            row.setdefault("rejection_id", None)
        item = {"股票代码": self.股票代码, "股票名称": 获取股票名称(self.股票代码)}
        item.update(row)
        self.账户.审批记录.append(item)
        result = str(row.get("结果", ""))
        reason = str(row.get("原因", ""))
        if result:
            self.账户.审批统计[result] += 1
        if reason:
            self.账户.审批统计[reason] += 1


class 交易账户:
    """可供一个或多个股票执行器共享的真实账户。"""

    def __init__(self, initial_cash):
        self.初始资金 = float(initial_cash)
        self.现金 = float(initial_cash)
        self.持仓 = {}
        self.最新价格 = {}
        self.审批记录 = []
        self.审批统计 = defaultdict(int)
        self.拒绝序号 = 0

    def 股票视图(self, stock):
        return 股票账户视图(self, stock)

    def 持仓市值(self):
        total = 0.0
        for stock, position in self.持仓.items():
            price = self.最新价格.get(_规范股票代码(stock))
            if price is None:
                price = position.get("买入价", 0)
            total += float(position.get("股数", 0) or 0) * float(price or 0)
        return total

    def 权益(self):
        return self.现金 + self.持仓市值()

    def 快照(self):
        market_value = self.持仓市值()
        equity = self.现金 + market_value
        return {
            "初始资金": self.初始资金,
            "现金": self.现金,
            "持仓市值": market_value,
            "权益": equity,
            "资金使用率": market_value / max(equity, 1.0),
            "持仓数量": len(self.持仓),
        }


class 单股账户(交易账户):
    """单股模式使用的账户类型；行为与交易账户完全相同。"""
