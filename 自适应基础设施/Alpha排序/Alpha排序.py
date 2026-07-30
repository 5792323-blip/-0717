"""基于可靠价量数据的横截面排序，只计算不交易。"""

import numpy as np
import pandas as pd


class Alpha排序器:
    def __init__(self, sessions):
        self.sessions = sessions

    @staticmethod
    def _百分位(values, higher=True):
        series = pd.Series(values, dtype=float).replace([np.inf, -np.inf], np.nan)
        return series.rank(pct=True, ascending=higher)

    def 计算(self, date):
        current = pd.Timestamp(str(date)[:10])
        rows = []
        for session in self.sessions:
            data = session["数据"]
            dates = data["日期"].astype(str).str[:10]
            history = data[dates < current.strftime("%Y-%m-%d")]
            if len(history) < 61:
                continue
            close = pd.to_numeric(history["不复权_收盘"], errors="coerce")
            amount = pd.to_numeric(history.get("成交额", pd.Series(index=history.index)), errors="coerce")
            rs60 = close.iloc[-6] / close.iloc[-61] - 1 if close.iloc[-61] else np.nan
            path = close.iloc[-21:].diff().abs().sum()
            efficiency = abs(close.iloc[-1] - close.iloc[-21]) / path if path else np.nan
            volume_quality = amount.iloc[-20:].mean() / amount.iloc[-120:].mean() if len(amount) >= 120 and amount.iloc[-120:].mean() else np.nan
            atr = pd.to_numeric(history.get("ATR_14", pd.Series(index=history.index)), errors="coerce").iloc[-1]
            extension = abs(close.iloc[-1] / close.iloc[-20:].mean() - 1) / (atr / close.iloc[-1]) if atr and close.iloc[-1] else np.nan
            rows.append({"股票代码": session["股票代码"], "相对强度": rs60, "趋势效率": efficiency, "量价质量": volume_quality, "非过度延伸": -extension})
        if not rows:
            return {"生效日期": current.strftime("%Y-%m-%d"), "有效股票数": 0, "排名": []}
        frame = pd.DataFrame(rows).set_index("股票代码")
        scores = (
            0.40 * self._百分位(frame["相对强度"]) +
            0.25 * self._百分位(frame["趋势效率"]) +
            0.20 * self._百分位(frame["量价质量"]) +
            0.15 * self._百分位(frame["非过度延伸"])
        )
        frame["Alpha评分"] = scores
        frame = frame.dropna(subset=["Alpha评分"]).sort_values("Alpha评分", ascending=False)
        ranking = [{"股票代码": str(symbol), "Alpha评分": round(float(row["Alpha评分"]), 8), "排名": index}
                   for index, (symbol, row) in enumerate(frame.iterrows(), 1)]
        return {"生效日期": current.strftime("%Y-%m-%d"), "有效股票数": len(ranking), "排名": ranking,
                "候选股票": [item["股票代码"] for item in ranking[:max(1, int(len(ranking) * 0.15))]]}
