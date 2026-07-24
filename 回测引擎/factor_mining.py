#!/usr/bin/env python3
"""使用训练期日线数据和 Alphalens 挖掘复合因子。"""

import argparse
import json
import os
from datetime import datetime

import numpy as np
import pandas as pd
from alphalens import performance, utils


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
默认训练开始 = "2020-01-01"
默认训练结束 = "2023-12-31"
验证开始 = "2024-01-01"
验证结束 = "2026-07-01"


def 读取股票列表(path):
    with open(path, encoding="utf-8") as source:
        return list(dict.fromkeys(
            line.strip().replace("SH_", "").replace("SZ_", "")
            for line in source if line.strip()
        ))


def 加载日线(stock, start, end):
    path = os.path.join(项目根目录, "数据模块", "raw", f"{stock}_双价格合并.pkl")
    if not os.path.exists(path):
        return pd.DataFrame()
    bars = pd.read_pickle(path).copy()
    bars = bars[(bars["日期"] >= start) & (bars["日期"] <= end)]
    if bars.empty:
        return pd.DataFrame()
    bars["交易日"] = pd.to_datetime(bars["日期"].astype(str).str[:10])
    daily = bars.groupby("交易日").agg({
        "前复权_开盘": "first",
        "前复权_最高": "max",
        "前复权_最低": "min",
        "前复权_收盘": "last",
        "成交量": "sum",
        "RSI_14": "last",
        "ATR_14": "last",
    })
    daily.columns = ["open", "high", "low", "close", "volume", "rsi", "atr"]
    daily["asset"] = stock
    return daily.replace([np.inf, -np.inf], np.nan)


def 计算候选因子(daily):
    close = daily["close"]
    volume = daily["volume"]
    atr_safe = daily["atr"].replace(0, np.nan)
    range_safe = (daily["high"] - daily["low"]).replace(0, np.nan)
    volume_ratio = volume / volume.rolling(20, min_periods=10).mean()
    log_volume_ratio = np.log(volume_ratio.clip(lower=1e-6))
    momentum_5 = close.pct_change(5, fill_method=None)
    momentum_10 = close.pct_change(10, fill_method=None)
    rsi_change_3 = daily["rsi"].diff(3) / 100.0
    close_position = (close - daily["low"]) / range_safe - 0.5
    breakout_20 = (close - daily["high"].rolling(20, min_periods=10).max().shift(1)) / atr_safe
    atr_ratio = atr_safe / close.replace(0, np.nan)

    return pd.DataFrame({
        "动量_成交量": momentum_5 * log_volume_ratio,
        "实体强度_ATR": (close - daily["open"]) / atr_safe,
        "突破位置_成交量": breakout_20 * log_volume_ratio,
        "RSI偏离_ATR": ((daily["rsi"] - 50.0) / 50.0) * atr_ratio,
        "振幅_成交量": (range_safe / atr_safe) * log_volume_ratio,
        "收盘位置_RSI变化": close_position * rsi_change_3,
        "中期动量_RSI位置": momentum_10 * ((daily["rsi"] - 50.0) / 50.0),
        "跳空_ATR": ((daily["open"] - close.shift(1)) / atr_safe) * log_volume_ratio,
        "量价背离": momentum_5 * (-volume.pct_change(5, fill_method=None)),
        "ATR扩张_RSI变化": atr_ratio.pct_change(5, fill_method=None) * rsi_change_3,
    }, index=daily.index).replace([np.inf, -np.inf], np.nan)


def 构建训练面板(stocks, start, end):
    factors = []
    closes = []
    loaded = []
    for stock in stocks:
        daily = 加载日线(stock, start, end)
        if len(daily) < 80:
            continue
        candidate = 计算候选因子(daily)
        candidate["asset"] = stock
        candidate = candidate.set_index("asset", append=True)
        factors.append(candidate)
        closes.append(daily["close"].rename(stock))
        loaded.append(stock)
    if not factors:
        raise RuntimeError("训练区间没有足够的股票数据")
    return pd.concat(factors).sort_index(), pd.concat(closes, axis=1).sort_index(), loaded


def 用Alphalens计算IC(series, prices, periods):
    factor = series.dropna().copy()
    factor.index = factor.index.set_names(["date", "asset"])
    clean = utils.get_clean_factor_and_forward_returns(
        factor,
        prices,
        periods=periods,
        quantiles=None,
        bins=5,
        max_loss=0.60,
        cumulative_returns=True,
    )
    ic = performance.factor_information_coefficient(clean)
    return {column: float(ic[column].mean()) for column in ic.columns}, len(clean)


def 挖掘(stocks, start, end, periods, top_n):
    if end >= 验证开始:
        raise ValueError(f"训练结束日期必须早于封存验证期 {验证开始}")
    panel, prices, loaded = 构建训练面板(stocks, start, end)
    ranking = []
    for name in panel.columns:
        ic_by_period, observations = 用Alphalens计算IC(panel[name], prices, periods)
        mean_ic = float(np.mean(list(ic_by_period.values())))
        mean_abs_ic = float(np.mean([abs(value) for value in ic_by_period.values()]))
        values = panel[name].dropna()
        std = float(values.std(ddof=0))
        ranking.append({
            "名称": name,
            "各周期IC": ic_by_period,
            "平均IC": mean_ic,
            "平均绝对IC": mean_abs_ic,
            "方向": 1 if mean_ic >= 0 else -1,
            "训练均值": float(values.mean()),
            "训练标准差": std if std > 1e-12 else 1.0,
            "有效样本数": observations,
        })
    ranking.sort(key=lambda item: item["平均绝对IC"], reverse=True)
    selected = ranking[:top_n]
    weight_sum = sum(item["平均绝对IC"] for item in selected) or 1.0
    for item in selected:
        item["权重"] = item["平均绝对IC"] / weight_sum
    return ranking, selected, loaded


def 写出结果(ranking, selected, loaded, args):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.abspath(args.output_dir or os.path.join(
        项目根目录, "10_实验记录", f"因子挖掘_{timestamp}"
    ))
    os.makedirs(output_dir, exist_ok=True)
    model = {
        "模型版本": timestamp,
        "训练区间": [args.start, args.end],
        "封存验证区间": [验证开始, 验证结束],
        "未来收益周期_交易日": args.periods,
        "训练股票": loaded,
        "得分阈值": 0.0,
        "因子": selected,
        "声明": "所有因子选择、方向、权重、均值和标准差仅由训练期生成；验证期不得重算。",
    }
    model_path = os.path.abspath(args.model_output)
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    with open(model_path, "w", encoding="utf-8") as target:
        json.dump(model, target, ensure_ascii=False, indent=2)
    with open(os.path.join(output_dir, "IC完整排名.json"), "w", encoding="utf-8") as target:
        json.dump(ranking, target, ensure_ascii=False, indent=2)
    with open(os.path.join(output_dir, "IC因子挖掘报告.md"), "w", encoding="utf-8") as target:
        target.write("# Alphalens IC复合因子挖掘报告\n\n")
        target.write(f"- 训练期：{args.start} 至 {args.end}\n")
        target.write(f"- 封存验证期：{验证开始} 至 {验证结束}（未参与本次计算）\n")
        target.write(f"- 股票数：{len(loaded)}；未来周期：{args.periods}个交易日\n")
        target.write("- 选择标准：各未来周期平均绝对IC，从高到低取前5。\n\n")
        target.write("| 排名 | 复合因子 | 平均IC | 平均绝对IC | 方向 | 权重 |\n")
        target.write("|---:|---|---:|---:|---:|---:|\n")
        for index, item in enumerate(selected, 1):
            target.write(
                f"| {index} | {item['名称']} | {item['平均IC']:.5f} | "
                f"{item['平均绝对IC']:.5f} | {item['方向']:+d} | {item['权重']:.3f} |\n"
            )
    return output_dir, model_path


def main():
    parser = argparse.ArgumentParser(description="Alphalens复合因子IC挖掘")
    parser.add_argument("--stocks", default=os.path.join(项目根目录, "top30.txt"))
    parser.add_argument("--start", default=默认训练开始)
    parser.add_argument("--end", default=默认训练结束)
    parser.add_argument("--periods", nargs="+", type=int, default=[1, 3, 5])
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--output-dir")
    parser.add_argument("--model-output", default=os.path.join(
        项目根目录, "1_策略配置", "扩展因子模型.json"
    ))
    args = parser.parse_args()
    stocks = 读取股票列表(args.stocks)
    ranking, selected, loaded = 挖掘(stocks, args.start, args.end, tuple(args.periods), args.top_n)
    output_dir, model_path = 写出结果(ranking, selected, loaded, args)
    print(json.dumps({"输出目录": output_dir, "模型": model_path, "前5因子": selected}, ensure_ascii=False))


if __name__ == "__main__":
    main()
