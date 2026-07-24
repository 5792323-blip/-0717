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


def _read_events(details):
    events = []
    prices = defaultdict(dict)
    for detail in details:
        stock = str(detail.get("股票代码", ""))
        path = os.path.join(detail.get("结果目录", ""), "交易明细.csv")
        holding_path = os.path.join(detail.get("结果目录", ""), "持仓过程.csv")
        if not stock or not os.path.isfile(path):
            continue
        if os.path.isfile(holding_path):
            try:
                holding = pd.read_csv(holding_path, encoding="utf-8-sig")
                for _, row in holding.iterrows():
                    timestamp = pd.to_datetime(row.get("日期"), errors="coerce")
                    price = _number(row.get("不复权收盘"))
                    if not pd.isna(timestamp) and price > 0:
                        prices[stock][timestamp] = price
            except (OSError, ValueError, pd.errors.ParserError):
                pass
        try:
            with open(path, encoding="utf-8-sig", newline="") as source:
                rows = csv.DictReader(source)
                for row in rows:
                    kind = str(row.get("类型", "")).strip()
                    timestamp = pd.to_datetime(row.get("时间"), errors="coerce")
                    if kind not in ("买入", "卖出") or pd.isna(timestamp):
                        continue
                    price_key = "买入价" if kind == "买入" else "卖出价"
                    price = _number(row.get(price_key))
                    shares = int(_number(row.get("成交数量")))
                    if price <= 0 or shares < 100:
                        continue
                    events.append({
                        "时间": timestamp,
                        "类型": kind,
                        "股票代码": stock,
                        "价格": price,
                        "股数": shares // 100 * 100,
                        "信号类型": row.get("信号类型", ""),
                        "信号质量分": _number(row.get("信号质量分"), 0.0),
                        "网格级别": int(_number(row.get("网格级别"))),
                        "网格层级标识": row.get("网格层级标识", ""),
                    })
        except (OSError, csv.Error):
            continue
    return (sorted(events, key=lambda item: (item["时间"], 0 if item["类型"] == "卖出" else 1, item["股票代码"])), prices)


def replay(details, capital, max_positions=30, max_single_ratio=0.03,
           max_total_ratio=0.80, cash_floor=0.20, max_daily_buy_ratio=0.05,
           stock_capital=None, initial_position_ratio=0.25,
           followup_position_ratio=0.25, candidate_expiry_bars=3):
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

    def target_for_next_layer(position):
        """Return cumulative target value for the next allocation layer."""
        layers = int(position.get("买入层数", 0)) if position else 0
        if layers <= 0:
            return stock_capital * float(initial_position_ratio)
        return min(
            stock_capital,
            stock_capital * (
                float(initial_position_ratio) + layers * float(followup_position_ratio)
            ),
        )

    def sell_position(stock, requested, price):
        position = positions.get(stock)
        if not position:
            return 0.0
        remaining = min(int(requested), position["shares"])
        remaining = remaining // 100 * 100
        if remaining < 100:
            return 0.0
        proceeds = remaining * price
        commission = max(proceeds * 0.00025, 5.0)
        tax = proceeds * 0.001
        transfer = proceeds * 0.00001
        net = proceeds - commission - tax - transfer
        position["shares"] -= remaining
        if position["shares"] <= 0:
            positions.pop(stock, None)
        return net

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
            before = positions[stock]["shares"]
            cash += sell_position(stock, event["股数"], price)
            filled = before - positions.get(stock, {}).get("shares", 0)
            if filled < 100:
                counters["卖出无有效成交"] += 1
                continue
            counters["卖出成交"] += 1
            audit_rows.append({"时间": timestamp.strftime("%Y-%m-%d %H:%M"), "股票代码": stock,
                               "类型": "卖出", "结果": "实际成交", "原因": event.get("信号类型", "卖出信号"),
                               "请求股数": event["股数"], "成交股数": filled, "成交价": price,
                               "网格层级": event.get("网格级别", 0)})

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

        buy_events = list(pending_candidates.values()) + [
            item for item in by_time[timestamp] if item["类型"] == "买入"
        ]
        for event in buy_events:
            if event.get("入队索引") is not None:
                event["价格"] = last_prices.get(event["股票代码"], event["价格"])
        buy_events.sort(key=signal_priority, reverse=True)
        counters["候选队列信号数"] += len(buy_events)
        for queue_index, event in enumerate(buy_events, 1):
            stock = event["股票代码"]
            price = event["价格"]
            last_prices[stock] = price

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
                    counters["最大持仓拦截"] += 1
                continue
            daily_limit = total_equity * float(max_daily_buy_ratio)
            if day_buy >= daily_limit:
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
            desired_value = max(event["股数"] * price, target_for_next_layer(position))
            allocation_value = max(0.0, desired_value - current_value)
            daily_remaining = max(0.0, daily_limit - day_buy)
            target = min(
                allocation_value, remaining_stock, remaining_total,
                available_cash, daily_remaining,
            )
            shares = int((target / price + 1e-9) / 100) * 100
            if shares < 100:
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
            if total_cost > cash:
                counters["现金不足拦截"] += 1
                audit_rows.append({"时间": timestamp.strftime("%Y-%m-%d %H:%M"), "股票代码": stock,
                                   "类型": "买入信号", "结果": "组合层拦截", "原因": "现金底线限制",
                                   "请求股数": event["股数"], "成交股数": 0, "成交价": price,
                                   "网格层级": event.get("网格级别", 0), "候选队列序号": queue_index,
                                   "候选排序得分": priority_score(event)})
                continue
            cash -= total_cost
            if stock not in positions:
                positions[stock] = {"shares": 0, "last_price": price, "cost": 0.0}
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
            audit_rows.append({"时间": timestamp.strftime("%Y-%m-%d %H:%M"), "股票代码": stock,
                               "类型": "买入", "结果": "实际成交", "原因": event.get("信号类型", "买入信号"),
                               "请求股数": event["股数"], "成交股数": shares, "成交价": price,
                               "网格层级": level, "目标仓位": round(desired_value, 2),
                               "候选队列序号": queue_index, "候选排序得分": priority_score(event)})
            if event["信号类型"].startswith("网格"):
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
    }
