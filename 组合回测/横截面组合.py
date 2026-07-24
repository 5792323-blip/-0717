#!/usr/bin/env python3
"""横截面排名共享资金组合；信号在前一交易日收盘形成，次日开盘调仓。"""

import math
import os

import numpy as np
import pandas as pd
import yaml


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
因子列表 = ["20日动量", "20日反转", "5日反转", "低波动", "成交活跃", "动量质量复合", "反转质量复合"]


def 读取交易成本(config_dir):
    with open(os.path.join(config_dir, "参数配置.yaml"), encoding="utf-8") as source:
        config = yaml.safe_load(source)
    costs = config.get("交易成本", {})
    return {
        "滑点": float(costs.get("滑点", 0.001)),
        "佣金": float(costs.get("佣金", 0.00025)),
        "印花税": float(costs.get("印花税", 0.001)),
        "过户费": float(costs.get("过户费", 0.00001)),
    }


def 聚合日线(bars):
    if bars is None or bars.empty:
        return pd.DataFrame()
    data = bars.copy()
    data["交易日"] = pd.to_datetime(data["日期"].astype(str).str[:10])
    aggregations = {
        "前复权_开盘": "first",
        "前复权_最高": "max",
        "前复权_最低": "min",
        "前复权_收盘": "last",
        "成交额": "sum",
    }
    daily = data.groupby("交易日").agg(aggregations).rename(columns={
        "前复权_开盘": "open",
        "前复权_最高": "high",
        "前复权_最低": "low",
        "前复权_收盘": "close",
        "成交额": "amount",
    })
    daily = daily.sort_index()
    returns = daily["close"].pct_change(fill_method=None)
    daily["momentum_20"] = daily["close"].pct_change(20, fill_method=None)
    daily["reversal_5"] = -daily["close"].pct_change(5, fill_method=None)
    daily["low_volatility_20"] = -returns.rolling(20, min_periods=20).std(ddof=0)
    daily["liquidity_20"] = np.log(
        daily["amount"].rolling(20, min_periods=20).mean().where(lambda value: value > 0)
    )
    return daily.replace([np.inf, -np.inf], np.nan)


def 加载面板(stocks, start, end):
    raw_dir = os.path.join(项目根目录, "数据模块", "raw")
    daily_by_stock = {}
    for stock in stocks:
        path = os.path.join(raw_dir, f"{stock}_双价格合并.pkl")
        if not os.path.exists(path):
            continue
        bars = pd.read_pickle(path)
        # 保留训练开始前的少量数据作为指标预热，不产生区间外交易。
        dates = pd.to_datetime(bars["日期"].astype(str).str[:10])
        warmup_start = pd.Timestamp(start) - pd.Timedelta(days=120)
        bars = bars[(dates >= warmup_start) & (dates <= pd.Timestamp(end))]
        daily = 聚合日线(bars)
        if len(daily) >= 40:
            daily_by_stock[stock] = daily
    return daily_by_stock


def 构建矩阵(daily_by_stock, column, calendar):
    values = {
        stock: daily[column].reindex(calendar)
        for stock, daily in daily_by_stock.items()
    }
    return pd.DataFrame(values, index=calendar, dtype=float)


def 横截面分数(feature_matrices, signal_date, universe, factor):
    def rank(column, ascending=True):
        values = feature_matrices[column].loc[signal_date, universe].replace([np.inf, -np.inf], np.nan)
        return values.rank(pct=True, ascending=ascending)

    momentum = rank("momentum_20")
    reversal = rank("reversal_5")
    low_volatility = rank("low_volatility_20")
    liquidity = rank("liquidity_20")
    if factor == "20日动量":
        return momentum
    if factor == "20日反转":
        return 1.0 - momentum
    if factor == "5日反转":
        return reversal
    if factor == "低波动":
        return low_volatility
    if factor == "成交活跃":
        return liquidity
    if factor == "动量质量复合":
        return 0.5 * momentum + 0.3 * low_volatility + 0.2 * liquidity
    if factor == "反转质量复合":
        return 0.5 * reversal + 0.3 * low_volatility + 0.2 * liquidity
    raise ValueError(f"未知横截面因子: {factor}")


def 构建缓冲目标(scores, current_holdings, top_k, retain_rank=None, max_replacements=None):
    """用当期排名构建目标持仓；保留区和替换上限只影响旧持仓退出。"""
    ranked = scores.sort_values(ascending=False).index.tolist()
    if not ranked or top_k <= 0:
        return []
    incumbents = [stock for stock in ranked if stock in current_holdings]
    if not incumbents:
        return ranked[:top_k]

    rank_by_stock = {stock: rank for rank, stock in enumerate(ranked, 1)}
    effective_retain_rank = top_k if retain_rank is None else max(top_k, int(retain_rank))
    retained = [stock for stock in incumbents if rank_by_stock[stock] <= effective_retain_rank]

    if max_replacements is not None:
        minimum_incumbents = max(0, min(len(incumbents), top_k) - int(max_replacements))
        for stock in incumbents:
            if len(retained) >= minimum_incumbents:
                break
            if stock not in retained:
                retained.append(stock)

    selected = sorted(retained, key=rank_by_stock.get)[:top_k]
    for stock in ranked:
        if len(selected) >= top_k:
            break
        if stock not in selected:
            selected.append(stock)
    return selected


def 选择股票(
    feature_matrices, signal_date, trade_date, universe, factor, top_k, open_prices,
    current_holdings=None, retain_rank=None, max_replacements=None,
):
    scores = 横截面分数(feature_matrices, signal_date, universe, factor).dropna()
    tradable = open_prices.loc[trade_date].dropna()
    tradable = tradable[tradable > 0].index
    scores = scores[scores.index.isin(tradable)]
    selected = 构建缓冲目标(
        scores, current_holdings or {}, top_k, retain_rank, max_replacements
    )
    return selected, scores.to_dict()


def 交易费用(value, side, costs):
    if value <= 0:
        return 0.0
    commission = max(value * costs["佣金"], 5.0)
    transfer = value * costs["过户费"]
    stamp = value * costs["印花税"] if side == "卖出" else 0.0
    return commission + transfer + stamp


def 运行组合(
    daily_by_stock,
    universe,
    factor,
    start,
    end,
    costs,
    initial_capital=20_000_000,
    top_k=5,
    target_gross=0.80,
    rebalance_every=5,
    market_regime=None,
    retain_rank=None,
    max_replacements=None,
):
    universe = [stock for stock in universe if stock in daily_by_stock]
    calendar = sorted(set().union(*(daily_by_stock[stock].index for stock in universe)))
    calendar = pd.DatetimeIndex([date for date in calendar if pd.Timestamp(start) <= date <= pd.Timestamp(end)])
    if len(calendar) < 2:
        raise RuntimeError("组合区间没有足够交易日")
    columns = ["open", "close", "momentum_20", "reversal_5", "low_volatility_20", "liquidity_20"]
    matrices = {column: 构建矩阵(daily_by_stock, column, calendar) for column in columns}
    open_prices = matrices["open"]
    close_prices = matrices["close"]
    last_prices = close_prices.ffill()

    cash = float(initial_capital)
    holdings = {}
    equity_rows = []
    trade_rows = []
    total_turnover = 0.0
    rebalance_count = 0
    last_selection = []

    def mark_equity(date, prices):
        market_value = 0.0
        for stock, shares in holdings.items():
            price = prices.get(stock)
            if price is None or pd.isna(price) or price <= 0:
                price = last_prices.loc[date].get(stock)
            if price is not None and pd.notna(price) and price > 0:
                market_value += shares * float(price)
        return cash + market_value, market_value

    for index, trade_date in enumerate(calendar):
        signal_date = calendar[index - 1] if index > 0 else None
        is_rebalance = index > 0 and index % rebalance_every == 0
        if is_rebalance:
            risk_off = False
            if market_regime is not None:
                regime_value = market_regime.reindex([signal_date]).iloc[0]
                risk_off = pd.isna(regime_value) or not bool(regime_value)
            if risk_off:
                selected, scores = [], {}
            else:
                selected, scores = 选择股票(
                    matrices, signal_date, trade_date, universe, factor, top_k, open_prices,
                    holdings, retain_rank, max_replacements,
                )
            # 风险关闭时允许空选股并清仓；普通空选股仍跳过调仓。
            if selected or risk_off:
                open_row = open_prices.loc[trade_date]
                equity_open, _ = mark_equity(trade_date, open_row)
                target_value = equity_open * target_gross / len(selected) if selected else 0.0

                # 先卖出和减仓，再使用释放的现金买入。
                for stock in list(holdings):
                    raw_open = open_row.get(stock)
                    if raw_open is None or pd.isna(raw_open) or raw_open <= 0:
                        continue
                    target_shares = (
                        int(target_value / float(raw_open) / 100) * 100
                        if stock in selected else 0
                    )
                    current_shares = holdings[stock]
                    if current_shares <= target_shares:
                        continue
                    shares = current_shares - target_shares
                    price = float(raw_open) * (1 - costs["滑点"])
                    value = shares * price
                    fee = 交易费用(value, "卖出", costs)
                    cash += value - fee
                    total_turnover += value
                    trade_rows.append({
                        "日期": trade_date.isoformat(), "股票代码": stock, "方向": "卖出",
                        "股数": shares, "价格": price, "成交额": value, "费用": fee,
                        "因子": factor, "分数": scores.get(stock),
                    })
                    if target_shares:
                        holdings[stock] = target_shares
                    else:
                        del holdings[stock]

                for stock in selected:
                    raw_open = open_row.get(stock)
                    if raw_open is None or pd.isna(raw_open) or raw_open <= 0:
                        continue
                    price = float(raw_open) * (1 + costs["滑点"])
                    target_shares = int(target_value / price / 100) * 100
                    current_shares = holdings.get(stock, 0)
                    shares = max(0, target_shares - current_shares)
                    while shares >= 100:
                        value = shares * price
                        fee = 交易费用(value, "买入", costs)
                        if value + fee <= cash:
                            break
                        shares -= 100
                    if shares < 100:
                        continue
                    value = shares * price
                    fee = 交易费用(value, "买入", costs)
                    cash -= value + fee
                    holdings[stock] = current_shares + shares
                    total_turnover += value
                    trade_rows.append({
                        "日期": trade_date.isoformat(), "股票代码": stock, "方向": "买入",
                        "股数": shares, "价格": price, "成交额": value, "费用": fee,
                        "因子": factor, "分数": scores.get(stock),
                    })
                rebalance_count += 1
                last_selection = selected

        equity, market_value = mark_equity(trade_date, close_prices.loc[trade_date])
        equity_rows.append({
            "日期": trade_date, "权益": equity, "现金": cash, "持仓市值": market_value,
            "持仓数": len(holdings), "入选股票": ",".join(last_selection),
        })

    curve = pd.DataFrame(equity_rows).set_index("日期")
    trades = pd.DataFrame(trade_rows)
    returns = curve["权益"].pct_change(fill_method=None).fillna(0.0)
    total_return = curve["权益"].iloc[-1] / initial_capital - 1
    years = max((curve.index[-1] - curve.index[0]).days / 365.25, 1 / 252)
    annual_return = (1 + total_return) ** (1 / years) - 1 if total_return > -1 else -1
    drawdown = ((curve["权益"].cummax() - curve["权益"]) / curve["权益"].cummax()).max()
    annual_volatility = returns.std(ddof=0) * math.sqrt(252)
    yearly = {}
    for year, frame in curve.groupby(curve.index.year):
        year_return = frame["权益"].iloc[-1] / frame["权益"].iloc[0] - 1
        year_drawdown = ((frame["权益"].cummax() - frame["权益"]) / frame["权益"].cummax()).max()
        yearly[str(year)] = {
            "收益率": float(year_return),
            "最大回撤": float(year_drawdown),
            "期末权益": float(frame["权益"].iloc[-1]),
        }
    return {
        "因子": factor,
        "股票数": len(universe),
        "TopK": top_k,
        "保留排名": retain_rank,
        "每次最大替换数": max_replacements,
        "初始资金": initial_capital,
        "最终权益": float(curve["权益"].iloc[-1]),
        "总收益率": float(total_return),
        "年化收益率": float(annual_return),
        "最大回撤": float(drawdown),
        "年化波动率": float(annual_volatility),
        "收益回撤比": float(annual_return / max(drawdown, 1e-9)),
        "调仓次数": rebalance_count,
        "成交笔数": len(trades),
        "累计双边换手": float(total_turnover / initial_capital),
        "年度": yearly,
        "权益曲线": curve,
        "交易明细": trades,
    }
