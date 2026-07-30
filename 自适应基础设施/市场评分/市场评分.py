"""只计算、不拦截交易的市场评分。"""

import os
import pandas as pd


class 市场评分器:
    def __init__(self, 基准路径, sessions=None):
        self.指数 = pd.read_pickle(基准路径).copy() if os.path.exists(基准路径) else pd.DataFrame()
        if not self.指数.empty:
            self.指数["date"] = pd.to_datetime(self.指数["date"]).dt.normalize()
            self.指数 = self.指数.sort_values("date").drop_duplicates("date")
            self.指数["收益60"] = self.指数["close"].pct_change(60)
            self.指数["均线60"] = self.指数["close"].rolling(60, min_periods=60).mean()
            self.指数["波动20"] = self.指数["close"].pct_change().rolling(20, min_periods=20).std(ddof=0)
        self.sessions = sessions or []
        self._确认状态 = "历史不足"
        self._候选状态 = None
        self._候选连续天数 = 0
        self._危机恢复连续天数 = 0

    @staticmethod
    def _百分位(series, value):
        values = pd.to_numeric(series, errors="coerce").dropna()
        if len(values) < 20 or pd.isna(value):
            return None
        return float((values <= float(value)).mean())

    def 计算(self, date):
        current = pd.Timestamp(str(date)[:10]).normalize()
        history = self.指数[self.指数["date"] < current]
        if history.empty:
            return {"状态": "历史不足", "市场评分": None, "有效": False}
        row = history.iloc[-1]
        pct = self._百分位(history["收益60"].tail(504), row.get("收益60"))
        trend = None
        parts = []
        if pct is not None:
            parts.append(pct)
        if pd.notna(row.get("均线60")):
            parts.append(1.0 if row["close"] > row["均线60"] else 0.0)
        if parts:
            trend = sum(parts) / len(parts)
        vol_pct = self._百分位(history["波动20"].tail(504), row.get("波动20"))
        stability = 1.0 - vol_pct if vol_pct is not None else None
        breadth_values = []
        for data in self.sessions:
            data = data[data["日期"].astype(str).str[:10] < current.strftime("%Y-%m-%d")]
            if len(data) < 20:
                continue
            close = pd.to_numeric(data["不复权_收盘"], errors="coerce")
            ma20 = close.rolling(20, min_periods=20).mean().iloc[-1]
            if pd.notna(ma20):
                breadth_values.append(float(close.iloc[-1] > ma20))
        breadth = sum(breadth_values) / len(breadth_values) if breadth_values else 0.5
        components = [(trend, 0.40), (breadth, 0.35), (stability, 0.25)]
        valid_components = [(value, weight) for value, weight in components if value is not None]
        weight_total = sum(weight for _, weight in valid_components)
        score = (
            sum(value * weight for value, weight in valid_components) / weight_total
            if weight_total else None
        )
        if score is None:
            state = "历史不足"
        elif score >= 0.70:
            state = "ATTACK"
        elif score >= 0.50:
            state = "NORMAL"
        elif score >= 0.35:
            state = "DEFENSE"
        else:
            state = "CRISIS"
        confirmed = self._更新确认状态(state)
        return {"状态": confirmed, "原始状态": state,
                "市场评分": round(float(score), 8) if score is not None else None, "有效": score is not None,
                "趋势分": trend, "广度分": breadth, "稳定度分": stability,
                "有效组件": [name for name, value in (("趋势", trend), ("广度", breadth), ("稳定度", stability)) if value is not None],
                "指数日期": str(row["date"].date()), "有效股票数": len(breadth_values),
                "生效日期": current.strftime("%Y-%m-%d")}

    def _更新确认状态(self, state):
        if state == "历史不足":
            return self._确认状态
        if state == "CRISIS":
            self._确认状态 = "CRISIS"
            self._候选状态 = None
            self._候选连续天数 = 0
            self._危机恢复连续天数 = 0
            return self._确认状态
        if self._确认状态 == "CRISIS":
            if state in ("ATTACK", "NORMAL", "DEFENSE"):
                self._危机恢复连续天数 += 1
                if self._危机恢复连续天数 < 5:
                    return "CRISIS"
                self._确认状态 = state
                self._候选状态 = None
                self._候选连续天数 = 0
                self._危机恢复连续天数 = 0
                return self._确认状态
            self._危机恢复连续天数 = 0
        if state == self._确认状态:
            self._候选状态 = None
            self._候选连续天数 = 0
            return self._确认状态
        if state == self._候选状态:
            self._候选连续天数 += 1
        else:
            self._候选状态 = state
            self._候选连续天数 = 1
        if self._候选连续天数 >= 3:
            self._确认状态 = state
            self._候选状态 = None
            self._候选连续天数 = 0
        return self._确认状态
