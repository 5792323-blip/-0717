"""把旧规则执行器的真实变化映射为标准审计事件。

适配器不持有账户引用，不执行策略，也不修改任何交易状态；执行前快照
必须复制关键数值，避免执行后可变对象被原地修改导致对账失真。
"""

from copy import deepcopy

from 自适应基础设施.标识管理.事件编号 import 生成编号
from 自适应基础设施.数据结构.接口 import 账户变化, 成交结果, 转为字典
from 自适应基础设施.守恒检查.检查器 import 检查资金守恒, 检查持仓守恒, 检查非负状态


class 旧执行器适配器:
    def __init__(self, run_id, account_id, strategy_id, 日志=None):
        self.run_id = str(run_id)
        self.account_id = str(account_id)
        self.strategy_id = str(strategy_id)
        self.日志 = 日志
        self._序号 = 0

    @staticmethod
    def _现金(执行器):
        return float(getattr(执行器, "当前现金", 0.0) or 0.0)

    @staticmethod
    def _持仓(执行器, 股票代码):
        position = getattr(执行器, "当前持仓", {}).get(股票代码, {})
        return int(position.get("股数", 0) or 0)

    @staticmethod
    def _交易列表(执行器):
        recorder = getattr(执行器, "交易记录器", None)
        return list(getattr(recorder, "交易列表", []) or [])

    def 处理(self, 执行器, K线数据, 当前索引, 股票代码=None):
        """调用一次原有处理，并把新增真实成交映射为审计事件。"""
        股票代码 = str(股票代码 or getattr(执行器, "股票代码", "") or "")
        交易日期 = str(K线数据.get("日期", K线数据.get("完整时间", "")))
        现金前 = self._现金(执行器)
        持仓前 = self._持仓(执行器, 股票代码)
        交易前 = self._交易列表(执行器)
        # 复制交易记录，避免后续卖出回填买入记录影响本次差异判断。
        交易前快照 = deepcopy(交易前)
        执行器.每根K线处理(K线数据, 当前索引)
        现金后 = self._现金(执行器)
        持仓后 = self._持仓(执行器, 股票代码)
        交易后 = self._交易列表(执行器)
        新成交 = 交易后[len(交易前快照):]
        事件 = []
        for offset, trade in enumerate(新成交):
            self._序号 += 1
            类型 = str(trade.get("类型", ""))
            数量 = int(trade.get("成交数量", 0) or 0)
            价格字段 = "买入价" if 类型 == "买入" else "卖出价"
            价格 = trade.get(价格字段)
            总额 = float(trade.get("总成本", trade.get("仓位", 0)) or 0)
            费用 = float(trade.get("交易费用", 0) or 0)
            if 类型 == "买入":
                净现金 = -abs(总额)
                状态 = "FILLED"
            elif 类型 == "卖出":
                # 旧记录器把卖出净现金记为“卖出净金额”；不能用“仓位”
                # 代替，否则会把卖出成本误当成回款，导致资金守恒误报。
                净现金 = abs(float(
                    trade.get("卖出净金额", trade.get("成交净额", 0)) or 0
                ))
                状态 = "FILLED"
            else:
                continue
            intent_id = 生成编号("intent", self.run_id, self.account_id, 股票代码, 当前索引, offset, 类型)
            order_id = 生成编号("order", intent_id)
            execution_id = 生成编号("execution", order_id)
            result = 成交结果(
                execution_id=execution_id, order_id=order_id, intent_id=intent_id,
                symbol=股票代码, side="BUY" if 类型 == "买入" else "SELL",
                status=状态, requested_quantity=数量, filled_quantity=数量,
                execution_price=float(价格) if 价格 is not None else None,
                gross_amount=abs(float(价格 or 0) * 数量),
                commission=费用, stamp_tax=0.0, slippage_cost=0.0,
                net_cash_change=净现金,
                execution_time=str(trade.get("时间", 交易日期)),
            )
            事件.append(result)
            if self.日志:
                self.日志.记录("成交结果", 转为字典(result), 交易日期, 股票代码)

        买入数量 = sum(item.filled_quantity for item in 事件 if item.side == "BUY")
        卖出数量 = sum(item.filled_quantity for item in 事件 if item.side == "SELL")
        净现金变化 = sum(item.net_cash_change for item in 事件)
        checks = {
            "资金守恒": 检查资金守恒(现金前, 现金后, 净现金变化),
            "持仓守恒": 检查持仓守恒(持仓前, 持仓后, 买入数量, 卖出数量),
            "非负状态": 检查非负状态(现金后, 持仓后),
        }
        self._序号 += 1
        account_event = 账户变化(
            event_id=生成编号("account", self.run_id, self.account_id, 股票代码, 当前索引),
            run_id=self.run_id, account_id=self.account_id, event_sequence=self._序号,
            trade_date=交易日期, symbol=股票代码, event_type="每根K线处理",
            cash_before=现金前, cash_after=现金后, position_before=持仓前,
            position_after=持仓后, net_cash_change=净现金变化,
            intent_id=事件[-1].intent_id if 事件 else None,
            order_id=事件[-1].order_id if 事件 else None,
            execution_id=事件[-1].execution_id if 事件 else None,
            metadata={"当前索引": 当前索引, "守恒检查": checks},
        )
        if self.日志:
            self.日志.记录("账户变化", 转为字典(account_event), 交易日期, 股票代码)
            self.日志.记录("守恒检查", {
                "event_id": account_event.event_id, "守恒检查": checks,
            }, 交易日期, 股票代码)
        return {"成交结果": 事件, "账户变化": account_event, "守恒检查": checks}
