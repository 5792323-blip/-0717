#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Replay per-stock signals through one shared portfolio cash account."""

import csv
import os
from collections import defaultdict

import pandas as pd


def _number(value, default=0.0):
    try:
        value = float(value)
        return value if pd.notna(value) else default
    except (TypeError, ValueError):
        return default


def _minimum_trade_unit(stock):
    """Return the market lot size used by the portfolio allocator."""
    code = str(stock or "").strip().upper()
    for prefix in ("SH_", "SZ_", "BJ_"):
        if code.startswith(prefix):
            code = code[len(prefix):]
    if code.startswith(("688", "689")):
        return 200
    if code.startswith(("4", "8", "9")):
        return 300
    return 100


def _read_events(details):
    events = []
    prices = defaultdict(dict)
    for detail in details:
        stock = str(detail.get("股票代码", ""))
        candidate_path = os.path.join(detail.get("结果目录", ""), "候选交易明细.csv")
        path = candidate_path if os.path.isfile(candidate_path) else os.path.join(
            detail.get("结果目录", ""), "交易明细.csv"
        )
        holding_path = os.path.join(detail.get("结果目录", ""), "持仓过程.csv")
        if not stock or not os.path.isfile(path):
            continue
        if os.path.isfile(holding_path):
            try:
                holding = pd.read_csv(holding_path, encoding="utf-8-sig")
                for _, row in holding.iterrows():
                    timestamp = pd.to_datetime(
                        row.get("K线时间") or row.get("时间") or row.get("日期"),
                        errors="coerce",
                    )
                    price = _number(row.get("不复权收盘"))
                    if not pd.isna(timestamp) and price > 0:
                        prices[stock][timestamp] = price
            except (OSError, ValueError, pd.errors.ParserError):
                pass
        try:
            with open(path, encoding="utf-8-sig", newline="") as source:
                rows = csv.DictReader(source)
                for row_index, row in enumerate(rows, 1):
                    kind = str(row.get("类型", "")).strip()
                    timestamp = pd.to_datetime(
                        row.get("K线时间") or row.get("时间"), errors="coerce"
                    )
                    if kind not in ("买入", "卖出") or pd.isna(timestamp):
                        continue
                    price_key = "买入价" if kind == "买入" else "卖出价"
                    price = _number(row.get(price_key))
                    shares = int(_number(row.get("成交数量")))
                    unit = _minimum_trade_unit(stock)
                    if price <= 0 or shares < unit:
                        continue
                    events.append({
                        "时间": timestamp,
                        "类型": kind,
                        "股票代码": stock,
                        "价格": price,
                        "股数": shares // unit * unit,
                        "信号类型": row.get("信号类型", ""),
                        "信号质量分": _number(row.get("信号质量分"), 0.0),
                        "网格级别": int(_number(row.get("网格级别"))),
                        "网格层级标识": row.get("网格层级标识", ""),
                        "源序号": row.get("序号", row_index),
                        "源持仓组ID": row.get("持仓组ID", stock),
                        "源事件ID": f"{stock}:{row.get('序号', row_index)}:{kind}:{timestamp.strftime('%Y%m%d%H%M')}",
                    })
        except (OSError, csv.Error):
            continue
    return (sorted(events, key=lambda item: (item["时间"], 0 if item["类型"] == "卖出" else 1, item["股票代码"])), prices)


def replay(details, capital, max_positions=30, max_single_ratio=0.03,
           max_total_ratio=0.80, cash_floor=0.20, max_daily_buy_ratio=0.05,
           stock_capital=None, grid_mode="fixed_tranche",
           initial_position_ratio=0.25, followup_position_ratio=0.25,
           grid_multiplier=2.0, max_add_count=5, candidate_expiry_bars=3):
    """Replay signals with portfolio-level cash competition and audit counters."""
    initial = float(capital)
    stock_capital = float(stock_capital or initial * max_single_ratio)
    cash = initial
    positions = {}
    last_prices = {}
    counters = defaultdict(int)
    curve = []
    audit_rows = []
    pending_candidates = {}
    events, market_prices = _read_events(details)
    by_time = defaultdict(list)
    for event in events:
        by_time[event["时间"]].append(event)

    def market_value():
        return sum(item["shares"] * item["last_price"] for item in positions.values())

    def equity():
        return cash + market_value()

    def signal_priority(event):
        """Rank simultaneous entries before spending shared cash."""
        signal = str(event.get("信号类型", ""))
        strength = {
            "RSI上穿20": 4,
            "RSI上穿30": 3,
            "RSI上穿均线": 2,
            "RSI上穿70": 1,
        }.get(signal, 0)
        quality = _number(event.get("信号质量分"), 0.0)
        is_grid = 1 if signal.startswith("网格") else 0
        return (is_grid, quality, strength, str(event["股票代码"]))

    def priority_score(event):
        signal = str(event.get("信号类型", ""))
        strength = {"RSI上穿20": 4, "RSI上穿30": 3,
                    "RSI上穿均线": 2, "RSI上穿70": 1}.get(signal, 0)
        return round(
            (1 if signal.startswith("网格") else 0) * 100
            + _number(event.get("信号质量分"), 0.0) * 10
            + strength,
            4,
        )

    def target_shares_for_next_layer(position, event, price):
        """Return cumulative target shares; money remains a risk constraint."""
        unit = _minimum_trade_unit(event.get("股票代码", ""))
        layers = int(position.get("买入层数", 0)) if position else 0
        if layers <= 0:
            budget_shares = int(
                stock_capital * float(initial_position_ratio) / max(price, 1e-9) / unit
            ) * unit
            requested_shares = int(event.get("股数", 0) or 0) // unit * unit
            return max(unit, budget_shares, requested_shares)
        if layers > int(max_add_count):
            return int(position.get("股数", 0) or 0)
        initial_shares = int(position.get("首笔股数", 0) or 0)
        if str(grid_mode) == "multiplier":
            cumulative = sum(float(grid_multiplier) ** index for index in range(layers + 1))
            return int(initial_shares * cumulative / unit) * unit
        if str(grid_mode) == "linear":
            cumulative = sum(range(1, layers + 2))
            return int(initial_shares * cumulative / unit) * unit
        tranche = max(
            unit,
            int(initial_shares * float(followup_position_ratio)
                / max(float(initial_position_ratio), 1e-9) / unit) * unit,
        )
        return initial_shares + tranche * layers

    def sell_position(stock, requested, price):
        position = positions.get(stock)
        if not position:
            return None
        unit = _minimum_trade_unit(stock)
        remaining = min(int(requested), position["shares"])
        remaining = remaining // unit * unit
        if remaining < unit:
            return None
        proceeds = remaining * price
        commission = max(proceeds * 0.00025, 5.0)
        tax = proceeds * 0.001
        transfer = proceeds * 0.00001
        net = proceeds - commission - tax - transfer
        position["shares"] -= remaining
        if position["shares"] <= 0:
            positions.pop(stock, None)
        return {
            "成交股数": remaining,
            "交易费用": commission + tax + transfer,
            "成交净额": net,
        }

    timeline = sorted(set(by_time).union(
        timestamp for series in market_prices.values() for timestamp in series
    ))
    for timeline_index, timestamp in enumerate(timeline):
        day_buy = 0.0
        for stock, series in market_prices.items():
            if timestamp in series:
                last_prices[stock] = series[timestamp]
        for event in [item for item in by_time[timestamp] if item["类型"] == "卖出"]:
            stock = event["股票代码"]
            price = event["价格"]
            last_prices[stock] = price
            if stock not in positions:
                counters["卖出无持仓"] += 1
                audit_rows.append({"时间": timestamp.strftime("%Y-%m-%d %H:%M"), "股票代码": stock,
                                   "类型": "卖出信号", "结果": "组合层拦截", "原因": "组合层无持仓",
                                   "请求股数": event["股数"], "成交股数": 0, "成交价": price,
                                   "网格层级": ""})
                continue
            fill = sell_position(stock, event["股数"], price)
            if not fill:
                counters["卖出无有效成交"] += 1
                continue
            cash += fill["成交净额"]
            filled = fill["成交股数"]
            counters["卖出成交"] += 1
            trade_id = f"{stock}:S:{counters['卖出成交']}:{timestamp.strftime('%Y%m%d%H%M')}"
            audit_rows.append({"时间": timestamp.strftime("%Y-%m-%d %H:%M"), "股票代码": stock,
                               "类型": "卖出", "结果": "实际成交", "原因": event.get("信号类型", "卖出信号"),
                               "请求股数": event["股数"], "成交股数": filled, "成交价": price,
                               "网格层级": event.get("网格级别", 0), "成交ID": trade_id,
                               "持仓组ID": stock, "源事件ID": event.get("源事件ID", ""),
                               "交易费用": round(fill["交易费用"], 4),
                               "成交净额": round(fill["成交净额"], 4)})

        # A sell can free a slot before the current bar's candidate queue runs.
        # Queued orders are intentionally carried forward, not re-created from
        # the original signal, so their expiry remains deterministic.

        expired = []
        for stock, candidate in pending_candidates.items():
            age = timeline_index - int(candidate.get("入队索引", timeline_index))
            if age > int(candidate_expiry_bars):
                expired.append(stock)
                counters["候选队列过期"] += 1
                audit_rows.append({
                    "时间": timestamp.strftime("%Y-%m-%d %H:%M"),
                    "股票代码": stock,
                    "类型": "买入信号",
                    "结果": "候选队列过期",
                    "原因": "超过候选有效期",
                    "请求股数": candidate["股数"],
                    "成交股数": 0,
                    "成交价": last_prices.get(stock, candidate["价格"]),
                    "候选队列序号": candidate.get("入队序号", 0),
                    "候选排序得分": priority_score(candidate),
                })
        for stock in expired:
            pending_candidates.pop(stock, None)

        fresh_events = [item for item in by_time[timestamp] if item["类型"] == "买入"]
        for event in fresh_events:
            stock = event["股票代码"]
            queued = pending_candidates.get(stock)
            if queued is not None:
                if signal_priority(event) > signal_priority(queued):
                    replacement = dict(event)
                    replacement["入队索引"] = queued["入队索引"]
                    replacement["入队序号"] = queued["入队序号"]
                    pending_candidates[stock] = replacement
                    counters["候选队列更新"] += 1
                else:
                    counters["候选队列重复"] += 1
        fresh_events = [
            event for event in fresh_events
            if event["股票代码"] not in pending_candidates
        ]
        buy_events = list(pending_candidates.values()) + fresh_events
        for event in buy_events:
            if event.get("入队索引") is not None:
                event["价格"] = last_prices.get(event["股票代码"], event["价格"])
        buy_events.sort(key=signal_priority, reverse=True)
        counters["候选队列信号数"] += len(buy_events)
        for queue_index, event in enumerate(buy_events, 1):
            stock = event["股票代码"]
            price = event["价格"]
            last_prices[stock] = price
            is_grid_addon = (
                stock in positions
                and str(event.get("信号类型", "")).startswith("网格")
            )

            total_equity = equity()
            current_value = positions.get(stock, {}).get("shares", 0) * price
            if stock not in positions and len(positions) >= int(max_positions):
                if event.get("入队索引") is None:
                    pending = dict(event)
                    pending["入队索引"] = timeline_index
                    pending["入队序号"] = queue_index
                    pending_candidates[stock] = pending
                    counters["候选队列进入"] += 1
                    audit_rows.append({"时间": timestamp.strftime("%Y-%m-%d %H:%M"), "股票代码": stock,
                                       "类型": "买入信号", "结果": "进入候选队列", "原因": "达到最大持仓数，等待名额",
                                       "请求股数": event["股数"], "成交股数": 0, "成交价": price,
                                       "网格层级": event.get("网格级别", 0), "候选队列序号": queue_index,
                                       "候选排序得分": priority_score(event)})
                else:
                    counters["候选队列等待"] += 1
                continue
            daily_limit = total_equity * float(max_daily_buy_ratio)
            if not is_grid_addon and day_buy >= daily_limit:
                counters["单日新增资金拦截"] += 1
                audit_rows.append({"时间": timestamp.strftime("%Y-%m-%d %H:%M"), "股票代码": stock,
                                   "类型": "买入信号", "结果": "组合层拦截", "原因": "超过单日新增资金上限",
                                   "请求股数": event["股数"], "成交股数": 0, "成交价": price,
                                   "网格层级": event.get("网格级别", 0), "候选队列序号": queue_index,
                                   "候选排序得分": priority_score(event)})
                continue
            remaining_stock = max(0.0, stock_capital - current_value)
            remaining_total = max(0.0, total_equity * float(max_total_ratio) - market_value())
            available_cash = max(0.0, cash - total_equity * float(cash_floor))
            position = positions.get(stock)
            desired_shares = target_shares_for_next_layer(position, event, price)
            allocation_value = max(
                0.0,
                (desired_shares - positions.get(stock, {}).get("shares", 0)) * price,
            )
            daily_remaining = max(0.0, daily_limit - day_buy)
            target = allocation_value if is_grid_addon else min(
                allocation_value, remaining_stock, remaining_total,
                available_cash, daily_remaining,
            )
            unit = _minimum_trade_unit(stock)
            shares = int((target / price + 1e-9) / unit) * unit
            if shares < unit:
                counters["资金不足拦截"] += 1
                audit_rows.append({"时间": timestamp.strftime("%Y-%m-%d %H:%M"), "股票代码": stock,
                                   "类型": "买入信号", "结果": "组合层拦截", "原因": "资金/仓位不足一手",
                                   "请求股数": event["股数"], "成交股数": 0, "成交价": price,
                                   "网格层级": event.get("网格级别", 0), "候选队列序号": queue_index,
                                   "候选排序得分": priority_score(event)})
                continue
            cost = shares * price
            commission = max(cost * 0.00025, 5.0)
            transfer = cost * 0.00001
            total_cost = cost + commission + transfer
            if not is_grid_addon and total_cost > cash:
                counters["现金不足拦截"] += 1
                audit_rows.append({"时间": timestamp.strftime("%Y-%m-%d %H:%M"), "股票代码": stock,
                                   "类型": "买入信号", "结果": "组合层拦截", "原因": "现金底线限制",
                                   "请求股数": event["股数"], "成交股数": 0, "成交价": price,
                                   "网格层级": event.get("网格级别", 0), "候选队列序号": queue_index,
                               "候选排序得分": priority_score(event)})
                continue
            cash -= total_cost
            if stock not in positions:
                positions[stock] = {
                    "shares": 0, "last_price": price, "cost": 0.0,
                    "首笔股数": shares,
                }
            position = positions[stock]
            old_cost = position["cost"]
            position["cost"] = old_cost + total_cost
            position["shares"] += shares
            position["last_price"] = price
            day_buy += total_cost
            counters["买入成交"] += 1
            pending_candidates.pop(stock, None)
            if event.get("入队索引") is not None:
                counters["候选队列成交"] += 1
            level = int(position.get("买入层数", 0))
            position["买入层数"] = level + 1
            trade_id = f"{stock}:B:{counters['买入成交']}:{timestamp.strftime('%Y%m%d%H%M')}"
            audit_rows.append({"时间": timestamp.strftime("%Y-%m-%d %H:%M"), "股票代码": stock,
                               "类型": "买入", "结果": "实际成交", "原因": event.get("信号类型", "买入信号"),
                               "请求股数": event["股数"], "成交股数": shares, "成交价": price,
                               "网格层级": level, "目标股数": int(desired_shares),
                               "候选队列序号": queue_index, "候选排序得分": priority_score(event),
                               "成交ID": trade_id, "持仓组ID": stock,
                               "源事件ID": event.get("源事件ID", ""),
                               "交易费用": round(commission + transfer, 4),
                               "成交净额": round(total_cost, 4)})
            if is_grid_addon:
                counters["网格加仓成交"] += 1

        for stock, item in positions.items():
            if stock in last_prices:
                item["last_price"] = last_prices[stock]
        current_value = market_value()
        current_equity = cash + current_value
        curve.append({
            "日期": timestamp.strftime("%Y-%m-%d %H:%M"),
            "权益": round(current_equity, 2),
            "现金": round(cash, 2),
            "持仓市值": round(current_value, 2),
            "资金使用率": round(current_value / max(current_equity, 1.0), 6),
            "持仓数量": len(positions),
        })

    values = pd.Series([point["权益"] for point in curve] or [initial])
    peak = values.cummax()
    drawdown = float(((peak - values) / peak.replace(0, 1)).max())
    final_equity = float(values.iloc[-1])
    stock_summary = {}
    for detail in details:
        stock = str(detail.get("股票代码", ""))
        if not stock:
            continue
        rows = [row for row in audit_rows if str(row.get("股票代码", "")) == stock]
        actual = [row for row in rows if row.get("结果") == "实际成交"]
        buys = [row for row in actual if row.get("类型") == "买入"]
        sells = [row for row in actual if row.get("类型") == "卖出"]
        buy_cash = sum(_number(row.get("成交净额"), _number(row.get("成交股数")) * _number(row.get("成交价"))) for row in buys)
        sell_cash = sum(_number(row.get("成交净额"), _number(row.get("成交股数")) * _number(row.get("成交价"))) for row in sells)
        position = positions.get(stock, {})
        shares = int(position.get("shares", 0) or 0)
        market = shares * _number(position.get("last_price"), last_prices.get(stock, 0.0))
        contribution = sell_cash - buy_cash + market
        stock_summary[stock] = {
            "实际买入": len(buys),
            "实际卖出": len(sells),
            "组合拦截": sum(1 for row in rows if row.get("结果") != "实际成交"),
            "期末股数": shares,
            "期末市值": round(market, 2),
            "收益贡献": round(contribution, 2),
            "收益贡献率": contribution / stock_capital if stock_capital else 0.0,
        }
    return {
        "模式": "共享资金池网格",
        "组合初始资金": initial,
        "组合最终权益": final_equity,
        "组合总收益率": final_equity / initial - 1 if initial else 0.0,
        "组合最大回撤": drawdown,
        "最大使用资金": max((point["持仓市值"] for point in curve), default=0.0),
        "最小使用资金": min((point["持仓市值"] for point in curve if point["持仓市值"] > 0), default=0.0),
        "当前现金": cash,
        "当前持仓数量": len(positions),
        "组合权益曲线": curve,
        "资金审计": dict(counters),
        "组合成交明细": audit_rows,
        "组合股票汇总": stock_summary,
    }
