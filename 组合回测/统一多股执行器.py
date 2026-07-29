"""多股共享账户时间轴。

每只股票拥有独立的规则执行器和指标状态，但所有执行器引用同一个真实
账户。订单价格、股数、费用、网格和卖出仍只由规则执行器计算；本模块
只负责时间调度、同时信号顺序和组合权益快照。
"""

import os
from collections import Counter
from time import perf_counter

import pandas as pd
import yaml

from 回测引擎.backtest_engine import 准备回测数据
from 策略引擎.交易账户 import 交易账户
from 策略引擎.规则执行器 import 规则执行器
from 数据模块.股票名称 import 获取股票名称


def _断管错误(error):
    return isinstance(error, BrokenPipeError) or getattr(error, "errno", None) == 32 or "Broken pipe" in str(error)


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
        "股票名称": 获取股票名称(session["股票代码"]),
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


def _可序列化审批值(value):
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass
    if isinstance(value, dict):
        return {str(key): _可序列化审批值(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_可序列化审批值(item) for item in value]
    return value


def _提取拒绝订单明细(审批记录):
    details = []
    for row in 审批记录:
        try:
            shares = int(float(row.get("成交股数", 0) or 0))
        except (TypeError, ValueError):
            shares = 0
        if str(row.get("结果", "")) == "实际成交" and shares > 0:
            continue
        details.append({
            str(key): _可序列化审批值(value)
            for key, value in row.items()
        })
        if "股票名称" not in details[-1]:
            details[-1]["股票名称"] = 获取股票名称(details[-1].get("股票代码"))
    return details


def 运行共享账户回测(
    stocks, start, end, capital, config_dir, liquidity_limit=0.01,
    allow_partial_fill=True, progress_callback=None, stop_requested=None,
    checkpoint_callback=None, benchmark_config=None, historical_constituents=None,
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
            errors.append({"股票代码": stock, "股票名称": 获取股票名称(stock), "错误": "无可用数据或数据不足100行"})
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
    actual_buys = actual_sells = rejected_orders = partial_fills = 0
    rejection_reasons = Counter()
    rejection_categories = Counter()
    realized_wins = realized_losses = 0
    total_fees = 0.0
    approval_cursor = 0
    peak_equity = float(capital)
    max_drawdown = 0.0
    stopped = False

    default_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    benchmark_config = benchmark_config or {
        "name": "沪深300", "benchmark_path": os.path.join(default_root, "数据模块", "大盘数据", "hs300_日K线.pkl"),
        "curve_key": "沪深300权益", "return_key": "沪深300收益率",
    }
    benchmark_key = benchmark_config["curve_key"]
    return_key = benchmark_config["return_key"]
    hs_path = benchmark_config["benchmark_path"]
    hs_map = {}
    if os.path.exists(hs_path):
        try:
            hs_data = pd.read_pickle(hs_path)
            hs_data["date"] = hs_data["date"].astype(str).str[:10]
            hs_map = dict(zip(hs_data["date"], pd.to_numeric(hs_data["close"], errors="coerce")))
        except (OSError, ValueError, KeyError):
            hs_map = {}
    hs_dates = sorted(hs_map)
    hs_cursor = -1
    # 基准收益必须从本次回测区间的起点归一化，不能使用指数文件的
    # 全历史首个点位，否则跨区间比较会把指数点位变化误报为收益率。
    benchmark_start = timestamps[0].strftime("%Y-%m-%d") if timestamps else ""
    if benchmark_start:
        eligible = [
            day for day in hs_dates
            if day <= benchmark_start and pd.notna(hs_map[day]) and float(hs_map[day]) > 0
        ]
        if eligible:
            hs_cursor = hs_dates.index(eligible[-1])
    hs_first = float(hs_map[hs_dates[hs_cursor]]) if hs_cursor >= 0 else 0.0

    for 时间轴索引, timestamp in enumerate(timestamps, 1):
        if stop_requested and stop_requested():
            stopped = True
            break
        entries = timeline[timestamp]
        # 开盘时所有股票价格均已知；组合审批不能读取本根收盘价。
        for session, _, row in entries:
            account.股票视图(session["股票代码"]).更新估值价(
                row.get("不复权_开盘")
            )
        entries.sort(key=lambda item: _会话优先级(item[0]), reverse=True)
        for session, 股票位置, row in entries:
            if historical_constituents is not None:
                session["运行参数"]["禁止新开仓"] = not historical_constituents.包含(
                    session["股票代码"], timestamp.strftime("%Y-%m-%d")
                )
            row_data = row.to_dict()
            row_data["_上一根RSI"] = session["上一根RSI"]
            row_data["_上一根最低价RSI"] = session["上一根最低价RSI"]
            session["执行器"].每根K线处理(row_data, 股票位置)
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

        new_approvals = account.审批记录[approval_cursor:]
        approval_cursor = len(account.审批记录)
        for row in new_approvals:
            shares = int(float(row.get("成交股数", 0) or 0))
            result = str(row.get("结果", ""))
            if result == "实际成交" and shares > 0:
                if row.get("类型") == "买入":
                    actual_buys += 1
                elif row.get("类型") == "卖出":
                    actual_sells += 1
                    try:
                        pnl = float(row.get("盈亏比例"))
                        if pnl > 0:
                            realized_wins += 1
                        elif pnl < 0:
                            realized_losses += 1
                    except (TypeError, ValueError):
                        pass
            else:
                rejected_orders += 1
                rejection_reasons[str(row.get("原因") or result or "未说明原因")] += 1
                rejection_categories[str(row.get("拒绝分类") or row.get("原因") or result or "未说明原因")] += 1
            if str(row.get("审批状态", "")) == "部分成交":
                partial_fills += 1
            try:
                total_fees += float(row.get("交易费用", 0) or 0)
            except (TypeError, ValueError):
                pass

        peak_equity = max(peak_equity, float(point["权益"]))
        drawdown = (peak_equity - float(point["权益"])) / max(peak_equity, 1.0)
        max_drawdown = max(max_drawdown, drawdown)
        date_key = point["日期"][:10]
        while hs_cursor + 1 < len(hs_dates) and hs_dates[hs_cursor + 1] <= date_key:
            hs_cursor += 1
        hs_value = float(hs_map[hs_dates[hs_cursor]]) if hs_cursor >= 0 else 0.0
        strategy_return = (float(point["权益"]) / max(float(capital), 1.0) - 1.0) * 100
        benchmark_return = (hs_value / hs_first - 1.0) * 100 if hs_first and hs_value else None
        live = {
            "当前权益": round(float(point["权益"]), 2),
            "策略收益率": round(strategy_return, 6),
            "基准名称": benchmark_config["name"],
            return_key: round(benchmark_return, 6) if benchmark_return is not None else None,
            "超额收益率": round(strategy_return - benchmark_return, 6) if benchmark_return is not None else None,
            "当前回撤": round(drawdown * 100, 6),
            "最大回撤": round(max_drawdown * 100, 6),
            "实际买入": actual_buys,
            "实际卖出": actual_sells,
            "实际成交": actual_buys + actual_sells,
            "审批请求": len(account.审批记录),
            "拒绝订单": rejected_orders,
            "拒绝原因汇总": dict(rejection_reasons),
            "拒绝分类汇总": dict(rejection_categories),
            "部分成交": partial_fills,
            "已实现盈利": realized_wins,
            "已实现亏损": realized_losses,
            "已平仓胜率": realized_wins / max(realized_wins + realized_losses, 1) * 100,
            "累计费用": round(total_fees, 2),
            "当前日期": point["日期"],
            "现金": round(float(point["现金"]), 2),
            "持仓市值": round(float(point["持仓市值"]), 2),
            "资金使用率": round(float(point["资金使用率"]) * 100, 6),
            "持仓数量": int(point.get("持仓数量", 0) or 0),
        }
        curve[-1].update({benchmark_key: round(hs_value / hs_first * capital, 2) if hs_first and hs_value else None})
        try:
            if progress_callback and (时间轴索引 == 1 or 时间轴索引 == len(timestamps) or 时间轴索引 % max(1, len(timestamps) // 100) == 0):
                progress_callback(
                    phase="共享账户时间轴回测", completed=时间轴索引, total=len(timestamps),
                    unit="时间点", trades=actual_buys + actual_sells, message=f"处理到 {point['日期']}",
                    approvals=len(account.审批记录), live={**live, "已处理时间点": 时间轴索引, "时间点总数": len(timestamps)},
                    拒绝订单明细=_提取拒绝订单明细(account.审批记录),
                    curve_point={**curve[-1], **live},
                )
            if checkpoint_callback and (时间轴索引 == 1 or 时间轴索引 == len(timestamps) or 时间轴索引 % max(1, len(timestamps) // 100) == 0):
                checkpoint_callback(
                    completed=时间轴索引, total=len(timestamps), phase="共享账户时间轴回测",
                    live={**live, "已处理时间点": 时间轴索引, "时间点总数": len(timestamps)},
                    curve_point={**curve[-1], **live},
                )
        except BrokenPipeError:
            stopped = True
            break
        except Exception as error:
            if _断管错误(error):
                stopped = True
                break
            raise

    # 停止请求可能恰好发生在最后一个时间点处理完成之后；循环没有
    # 下一轮时不会再次命中开头的检查，因此这里补一次最终检查。
    if stop_requested and stop_requested():
        stopped = True
    elapsed = perf_counter() - started
    snapshot = _读取配置快照(config_dir)
    results = [
        _整理股票结果(session, capital, snapshot, elapsed)
        for session in sessions.values()
    ]
    final_live = {
        "已处理时间点": len(curve),
        "时间点总数": len(timestamps),
        "当前权益": round(float(account.权益()), 2),
        "策略收益率": round((float(account.权益()) / max(float(capital), 1.0) - 1.0) * 100, 6),
        "基准名称": benchmark_config["name"],
        "最大回撤": round(max_drawdown * 100, 6),
        "实际买入": actual_buys,
        "实际卖出": actual_sells,
        "实际成交": actual_buys + actual_sells,
        "审批请求": len(account.审批记录),
        "拒绝订单": rejected_orders,
        "拒绝原因汇总": dict(rejection_reasons),
        "拒绝分类汇总": dict(rejection_categories),
        "部分成交": partial_fills,
        "已平仓胜率": realized_wins / max(realized_wins + realized_losses, 1) * 100,
        "累计费用": round(total_fees, 2),
        "现金": round(float(account.现金), 2),
        "持仓市值": round(float(account.持仓市值()), 2),
        "资金使用率": round(float(account.持仓市值()) / max(float(account.权益()), 1.0) * 100, 6),
        "持仓数量": len(account.持仓),
    }
    return {
        "账户": account,
        "股票结果": results,
        "错误": errors,
        "组合权益曲线": curve,
        "耗时": elapsed,
        "stopped": stopped,
        "live": final_live,
    }
