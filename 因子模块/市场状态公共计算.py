"""CMSF（市场状态演化）公共计算层。

只使用截至当前 K 线的行情构建状态；买入/卖出过滤读取上一根已完成
状态，避免把当前收盘数据回填到本根交易决策中。
"""

from collections import deque
import math

from 因子模块.因子基类 import 因子基类


class 市场状态因子基类(因子基类):
    指标键 = "MS"
    指标名称 = "市场状态"

    def __init__(self, 参数=None):
        super().__init__(参数)
        self.短周期 = int(self.参数.get("短周期", 20))
        self.长周期 = int(self.参数.get("长周期", 60))
        self.动量周期 = int(self.参数.get("动量周期", 20))
        self.峰值窗口 = int(self.参数.get("峰值窗口", 120))
        self.混乱窗口 = int(self.参数.get("混乱窗口", 20))
        self.生命周期参考 = max(1, int(self.参数.get("生命周期参考K线", 42)))
        self.价格 = deque(maxlen=max(self.长周期, self.峰值窗口, self.动量周期) + 2)
        self.成交量 = deque(maxlen=max(self.短周期, 2) + 1)
        self.状态历史 = deque(maxlen=self.峰值窗口 + 2)
        self.波动率历史 = deque(maxlen=self.峰值窗口 + 2)
        self.当前状态 = None
        self.可用状态 = None
        self.连续趋势K线 = 0

    @staticmethod
    def _值(data, *keys):
        for key in keys:
            value = data.get(key)
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                return value
        return None

    @staticmethod
    def _tanh(value):
        return math.tanh(float(value))

    def _EMA(self, values, period):
        if not values:
            return None
        alpha = 2.0 / (period + 1.0)
        ema = float(values[0])
        for value in values[1:]:
            ema += alpha * (float(value) - ema)
        return ema

    def 每根K线处理(self, K线数据, 全局状态):
        # 因子管理器在本根交易检查前调用；先保留旧状态供本根过滤使用。
        self.可用状态 = dict(self.当前状态) if self.当前状态 else None
        close = self._值(K线数据, "前复权_收盘", "收盘价")
        volume = self._值(K线数据, "成交量", "不复权_成交量")
        atr = self._值(K线数据, "ATR_14")
        if close is None or close <= 0:
            return {"可用": False, "原因": "收盘价无效"}
        self.价格.append(close)
        if volume is not None and volume >= 0:
            self.成交量.append(volume)

        prices = list(self.价格)
        ema_short = self._EMA(prices[-self.短周期:], self.短周期)
        ema_long = self._EMA(prices[-self.长周期:], self.长周期)
        trend = (ema_short - ema_long) / ema_long if ema_long else 0.0
        momentum = (close / prices[-self.动量周期 - 1] - 1.0) if len(prices) > self.动量周期 else 0.0
        volumes = list(self.成交量)
        volume_ratio = volume / (sum(volumes[-self.短周期:]) / len(volumes[-self.短周期:])) if volume and volumes else 1.0
        volatility = atr / close if atr is not None and atr > 0 else 0.0
        # 统一为有限、近似[-1, 1]的状态分量；这是状态编码，不是价格预测。
        trend_score = self._tanh(trend * 20.0)
        momentum_score = self._tanh(momentum * 10.0)
        volume_score = self._tanh(math.log(max(volume_ratio, 1e-8)))
        volatility_risk = self._tanh(volatility * 50.0)
        ms = max(0.0, min(100.0, 50.0 + 50.0 * (
            0.35 * trend_score + 0.30 * momentum_score
            + 0.20 * volume_score - 0.15 * volatility_risk
        )))
        previous_ms = self.状态历史[-1] if self.状态历史 else ms
        ctr = ms - previous_ms
        trend_threshold = float(self.参数.get("趋势启动阈值", 55.0))
        self.连续趋势K线 = self.连续趋势K线 + 1 if ms >= trend_threshold else 0
        states = list(self.状态历史) + [ms]
        peak = max(states[-self.峰值窗口:])
        cpd = max(0.0, (peak - ms) / max(peak, 1.0))
        # 买入端三个状态过滤指标。它们只描述已经收盘的状态；下一根
        # K 线的哨兵价触发才会读取，绝不参与本根成交价计算。
        ccr = cpd
        cri = ms - (states[-4] if len(states) > 3 else ms)
        self.波动率历史.append(volatility)
        volatility_window = sorted(self.波动率历史)
        if volatility_window:
            percentile_index = max(0, math.ceil(len(volatility_window) * 0.8) - 1)
            volatility_reference = volatility_window[percentile_index]
            csa = max(0.0, min(1.0, 1.0 - volatility / max(volatility_reference, 1e-12)))
        else:
            csa = 0.0
        state_change = ms - (states[-11] if len(states) > 10 else ms)
        price_change = close / prices[-11] - 1.0 if len(prices) > 10 else 0.0
        cdf = max(0.0, self._tanh(price_change * 10.0) * max(0.0, -self._tanh(state_change / 10.0))) * 100.0
        deltas = [b - a for a, b in zip(states[-self.混乱窗口 - 1:-1], states[-self.混乱窗口:])]
        signs = [1 if item > 0 else -1 if item < 0 else 0 for item in deltas]
        turns = sum(1 for a, b in zip(signs, signs[1:]) if a and b and a != b)
        cde = turns / max(len(signs) - 1, 1)
        cst = self.连续趋势K线
        ctr_risk = max(0.0, -ctr / 5.0) * 100.0
        ctrs = min(100.0, (
            0.30 * cdf + 0.25 * min(cst / self.生命周期参考, 1.0) * 100.0
            + 0.20 * cpd * 100.0 + 0.15 * cde * 100.0 + 0.10 * min(ctr_risk, 100.0)
        ))
        self.当前状态 = {
            "MS": round(ms, 6), "CTR": round(ctr, 6), "CST": cst,
            "CPD": round(cpd, 6), "CDF": round(cdf, 6), "CDE": round(cde, 6),
            "CTRS": round(ctrs, 6), "价格变化": round(price_change, 6),
            "状态变化": round(state_change, 6), "状态标签": (
                "衰减" if ctrs >= 60 else "成熟" if ms >= 60 else "健康" if ms >= 50 else "震荡"
            ),
            "CCR": round(ccr, 6), "CRI": round(cri, 6), "CSA": round(csa, 6),
        }
        self.状态历史.append(ms)
        return {"可用": True, **self.当前状态, "本根仅供下一根使用": True}

    def 买入前检查(self, K线数据, 全局状态):
        # CMSF 入场因子默认只审查首次哨兵开仓。网格加仓沿用原有逻辑，
        # 不能因研究型状态过滤器而改变既有持仓的加仓路径。
        if self.参数.get("仅哨兵开仓", True) and 全局状态.get("当前持仓"):
            return {"允许买入": True, "质量分调整": 1.0, "说明": "已有持仓，CMSF不拦截网格加仓"}
        state = self.可用状态
        if not state:
            return {"允许买入": True, "质量分调整": 1.0, "说明": "CMSF历史不足，未过滤"}
        threshold = self.参数.get("买入过滤阈值")
        if threshold is None:
            return {"允许买入": True, "质量分调整": 1.0, "说明": f"{self.指标名称}={state[self.指标键]:.3f}（观察）"}
        value = float(state[self.指标键])
        block_when_above = bool(self.参数.get("买入高值拦截", True))
        blocked = value >= float(threshold) if block_when_above else value <= float(threshold)
        return {
            "允许买入": not blocked, "质量分调整": 1.0,
            "说明": f"{self.指标名称}={value:.3f}" + ("，拦截哨兵价成交" if blocked else "，通过"),
            "CMSF": state,
        }

    def 卖出信号过滤(self, 持仓, K线数据, 全局状态, 卖出规则):
        state = self.可用状态
        threshold = self.参数.get("卖出放行阈值")
        if not state or threshold is None:
            return {"允许卖出": True, "说明": "CMSF未启用卖出过滤"}
        protected = set(self.参数.get("不拦截卖出规则", []) or [])
        rule_id = str(卖出规则.get("英文标识", ""))
        if rule_id in protected:
            return {"允许卖出": True, "说明": f"{rule_id}为保护性卖出，不拦截"}
        value = float(state[self.指标键])
        allow_when_above = bool(self.参数.get("卖出高值放行", True))
        allowed = value >= float(threshold) if allow_when_above else value <= float(threshold)
        return {
            "允许卖出": allowed,
            "说明": f"{self.指标名称}={value:.3f}" + ("，放行既有卖出" if allowed else "，暂缓既有卖出"),
            "CMSF": state,
        }

    def 重置(self):
        self.__init__(self.参数)
