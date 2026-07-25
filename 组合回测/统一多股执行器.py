"""多股共享账户时间轴。

每只股票拥有独立的规则执行器和指标状态，但所有执行器引用同一个真实
账户。订单价格、股数、费用、网格和卖出仍只由规则执行器计算；本模块
只负责时间调度、同时信号顺序和组合权益快照。
"""

import os
from time import perf_counter

import pandas as pd
import yaml

from 回测引擎.backtest_engine import 准备回测数据
from 策略引擎.交易账户 import 交易账户
from 策略引擎.规则执行器 import 规则执行器


def _时间键(index, row):
    value = row.get("完整时间", index)
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        timestamp = pd.to_datetime(row.get("日期"), errors="coerce")
    return timestamp


def _会话优先级(session):
    """同一时刻先处理已有持仓，再按待网格和哨兵强度排序。"""
    executor = session["执行器"]
    position = next(iter(executor.当前持仓.values()), {})
    pending_grid = int(position.get("网格_待加仓股数", 0) or 0) if position else 0
    signal = str(getattr(executor, "哨兵价形成类型", "") or "")
    signal_strength = {
        "RSI上穿20": 4,
        "RSI上穿30": 3,
        "RSI上穿均线": 2,
        "RSI上穿70": 1,
    }.get(signal, 0)
    return (
        1 if position else 0,
        1 if pending_grid else 0,
        signal_strength,
        str(session["股票代码"]),
    )


def _读取配置快照(config_dir):
    snapshot = {}
    for name in (
        "买入信号配置.yaml", "卖出规则配置.yaml", "仓位配置.yaml",
        "参数配置.yaml", "过滤因子配置.yaml", "因子配置.yaml",
        "核心模块配置.yaml", "模块开关配置.yaml",
    ):
        path = os.path.join(config_dir, name)
        with open(path, encoding="utf-8") as source:
            snapshot[name] = yaml.safe_load(source)
    return snapshot


def _整理股票结果(session, initial_capital, config_snapshot, elapsed):
    executor = session["执行器"]
    data = session["数据"]
    result = executor.获取结果(data.iloc[-1])
    trades = result["交易明细"]
    buys = trades[trades["类型"] == "买入"] if len(trades) else pd.DataFrame()
    sells = trades[trades["类型"] == "卖出"] if len(trades) else pd.DataFrame()
    pnl = pd.to_numeric(
        sells.get("盈亏比例", pd.Series(dtype=float)), errors="coerce"
    ).dropna()
    process_equity = pd.to_numeric(
        result["持仓过程"].get("权益", pd.Series(dtype=float)), errors="coerce"
    ).dropna()
    result.update({
        "股票代码": session["股票代码"],
        "初始资金": initial_capital,
        "原始K线数据": data,
        "数据行数": len(data),
        "买入次数": len(buys),
        "卖出次数": len(sells),
        "胜率": float((pnl > 0).mean() * 100) if len(pnl) else 0.0,
        "平均盈亏": float(pnl.mean() * 100) if len(pnl) else 0.0,
        "最大回撤": float(
            ((process_equity.cummax() - process_equity) / process_equity.cummax()).max() * 100
        ) if len(process_equity) else 0.0,
        "总收益率": (result["最终权益"] - initial_capital) / initial_capital * 100
        if initial_capital else 0.0,
        "盈亏比": float(pnl[pnl > 0].sum() / abs(pnl[pnl < 0].sum()))
        if len(pnl[pnl < 0]) and pnl[pnl < 0].sum() else None,
        "配置快照": config_snapshot,
        "运行参数": session["运行参数"],
        "耗时": elapsed,
    })
    return result


def 运行共享账户回测(
    stocks, start, end, capital, config_dir, liquidity_limit=0.01,
    allow_partial_fill=True, progress_callback=None,
):
    """在一个共享账户中直接运行多只股票，不产生候选成交。"""
    started = perf_counter()
    account = 交易账户(capital)
    sessions = {}
    errors = []
    timeline = {}
    config_dir = os.path.abspath(config_dir)

    for stock in stocks:
        data, _, _, _ = 准备回测数据(stock, start, end, config_dir)
        if data is None:
            errors.append({"股票代码": stock, "错误": "无可用数据或数据不足100行"})
            if progress_callback:
                progress_callback(
                    phase="加载股票数据", completed=len(sessions) + len(errors),
                    total=len(stocks), unit="股票", trades=0, message=f"跳过 {stock}：无可用数据",
                )
            continue
        runtime = {
            "流动性上限比例": liquidity_limit,
            "多股资金池模式": True,
            "共享账户模式": True,
            "允许部分成交": bool(allow_partial_fill),
        }
        executor = 规则执行器(
            config_dir, 运行参数=runtime, 账户=account, 股票代码=stock
        )
        session = {
            "股票代码": stock,
            "数据": data,
            "执行器": executor,
            "上一根RSI": 50,
            "上一根最低价RSI": 50,
            "运行参数": runtime,
        }
        sessions[stock] = session
        for position, (index, row) in enumerate(data.iterrows()):
            timestamp = _时间键(index, row)
            if pd.isna(timestamp):
                continue
            timeline.setdefault(timestamp, []).append((session, position, row))
        if progress_callback:
            progress_callback(
                phase="加载股票数据", completed=len(sessions) + len(errors),
                total=len(stocks), unit="股票", trades=0, message=f"已加载 {stock}",
            )

    curve = []
    timestamps = sorted(timeline)
    for position, timestamp in enumerate(timestamps, 1):
        entries = timeline[timestamp]
        # 开盘时所有股票价格均已知；组合审批不能读取本根收盘价。
        for session, _, row in entries:
            account.股票视图(session["股票代码"]).更新估值价(
                row.get("不复权_开盘")
            )
        entries.sort(key=lambda item: _会话优先级(item[0]), reverse=True)
        for session, position, row in entries:
            row_data = row.to_dict()
            row_data["_上一根RSI"] = session["上一根RSI"]
            row_data["_上一根最低价RSI"] = session["上一根最低价RSI"]
            session["执行器"].每根K线处理(row_data, position)
            session["上一根RSI"] = row.get("RSI_14", 50)
            session["上一根最低价RSI"] = row.get(
                "RSI_最低价", session["上一根RSI"]
            )
        # 收盘后更新组合净值，仅用于本根结束后的权益曲线。
        for session, _, row in entries:
            account.股票视图(session["股票代码"]).更新估值价(
                row.get("不复权_收盘")
            )
        point = account.快照()
        point["日期"] = timestamp.strftime("%Y-%m-%d %H:%M")
        curve.append(point)
        if progress_callback and (position == 1 or position == len(timestamps) or position % max(1, len(timestamps) // 100) == 0):
            progress_callback(
                phase="共享账户时间轴回测", completed=position, total=len(timestamps),
                unit="时间点", trades=len(account.审批记录), message=f"处理到 {point['日期']}",
            )

    elapsed = perf_counter() - started
    snapshot = _读取配置快照(config_dir)
    results = [
        _整理股票结果(session, capital, snapshot, elapsed)
        for session in sessions.values()
    ]
    return {
        "账户": account,
        "股票结果": results,
        "错误": errors,
        "组合权益曲线": curve,
        "耗时": elapsed,
    }
