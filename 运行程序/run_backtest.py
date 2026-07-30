#!/usr/bin/env python3
"""统一多股票回测入口，输出机器可读JSON。"""

import argparse
import contextlib
import io
import json
import math
import os
import sys
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor
from datetime import date

import pandas as pd

项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def 为交易证据添加股票范围编号(trades, stock):
    """为多股证据编号增加股票范围，避免各执行器从 1 重新编号。"""
    frame = trades.copy()
    stock = str(stock)
    if "股票代码" not in frame:
        frame.insert(0, "股票代码", stock)
    for field in ("intent_id", "order_id", "execution_id"):
        if field in frame:
            frame[field] = frame[field].map(
                lambda value: f"{stock}:{value}" if str(value).strip() else value
            )
    return frame
sys.path.insert(0, 项目根目录)

from 数据模块.股票名称 import 获取股票名称
from 模块系统 import 模块开关管理器
from 回测引擎.backtest_engine import 跑回测


def 读取股票列表(value):
    if os.path.isfile(value):
        with open(value, encoding="utf-8") as source:
            entries = [line.strip() for line in source if line.strip()]
    else:
        entries = [item.strip() for item in value.split(",") if item.strip()]
    stocks = [item.replace("SH_", "").replace("SZ_", "") for item in entries]
    return list(dict.fromkeys(stocks))


def 安全数值(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def 单股摘要(result, requested_start, requested_end):
    raw = result.get("原始K线数据")
    actual_start = str(raw["日期"].iloc[0])[:10]
    actual_end = str(raw["日期"].iloc[-1])[:10]
    actual_days = max(1, (date.fromisoformat(actual_end) - date.fromisoformat(actual_start)).days)
    requested_days = max(1, (date.fromisoformat(requested_end) - date.fromisoformat(requested_start)).days)
    years = max(1 / 252, actual_days / 365.25)
    total_return = 安全数值(result.get("总收益率")) / 100
    annual_return = (1 + total_return) ** (1 / max(years, 1 / 252)) - 1 if total_return > -1 else -1
    return {
        "股票代码": result.get("股票代码"),
        "股票名称": result.get("股票名称") or 获取股票名称(result.get("股票代码")),
        "买入次数": int(result.get("买入次数", 0)),
        "卖出次数": int(result.get("卖出次数", 0)),
        "胜率": 安全数值(result.get("胜率")) / 100,
        "总收益率": total_return,
        "年化收益率": annual_return,
        "最大回撤": 安全数值(result.get("最大回撤")) / 100,
        "盈亏比": 安全数值(result.get("盈亏比")),
        "最终权益": 安全数值(result.get("最终权益")),
        "数据开始": actual_start,
        "数据结束": actual_end,
        "数据覆盖率": min(1.0, actual_days / requested_days),
    }


def _格式化K线时间(value):
    try:
        timestamp = pd.to_datetime(value, errors="coerce")
    except (TypeError, ValueError):
        return ""
    if pd.isna(timestamp):
        return ""
    return timestamp.strftime("%Y-%m-%d %H:%M")


def _补充交易K线定位(trades, holding, raw):
    trades = trades.copy()
    holding = holding.copy() if holding is not None else pd.DataFrame()
    if raw is None or len(raw) == 0:
        return trades, holding

    kline_times = {}
    for position, (index, row) in enumerate(raw.iterrows()):
        value = row.get("完整时间", index)
        timestamp = _格式化K线时间(value)
        if not timestamp:
            timestamp = _格式化K线时间(row.get("日期"))
        kline_times[position] = timestamp

    if "K线索引" in holding.columns:
        holding["K线时间"] = holding["K线索引"].map(
            lambda value: kline_times.get(int(value), "") if pd.notna(value) else ""
        )

    candidates = {}
    if "K线索引" in holding.columns:
        for _, row in holding.iterrows():
            action = str(row.get("最终动作", ""))
            kind = "买入" if "买入" in action or "加仓" in action else "卖出" if "卖出" in action else ""
            if not kind:
                continue
            index = int(row["K线索引"])
            day = str(row.get("日期", ""))[:10]
            candidates.setdefault((day, kind), []).append({
                "K线索引": index,
                "K线时间": kline_times.get(index, ""),
                "序号": str(row.get("买入序号", "")),
                "持仓组ID": str(row.get("持仓组ID", "")),
            })

    used = set()
    located_indexes = []
    located_times = []
    for _, trade in trades.iterrows():
        day = str(trade.get("时间", ""))[:10]
        kind = str(trade.get("类型", ""))
        sequence = str(trade.get("序号", ""))
        group = str(trade.get("持仓组ID", ""))
        choices = candidates.get((day, kind), [])
        match = next((item for item in choices if item["K线索引"] not in used and sequence and item["序号"] == sequence), None)
        if match is None:
            match = next((item for item in choices if item["K线索引"] not in used and group and item["持仓组ID"] == group), None)
        if match is None:
            match = next((item for item in choices if item["K线索引"] not in used), None)
        if match is None:
            located_indexes.append(None)
            located_times.append(_格式化K线时间(trade.get("时间")))
            continue
        used.add(match["K线索引"])
        located_indexes.append(match["K线索引"])
        located_times.append(match["K线时间"])
    trades["K线索引"] = located_indexes
    trades["K线时间"] = located_times
    return trades, holding


def _保存多股单票结果(result, stock_dir):
    """保存多股本次运行的单票完整证据，不改变单股保存流程。"""
    os.makedirs(stock_dir, exist_ok=True)
    trades = result.get("交易明细")
    holding = result.get("持仓过程")
    if trades is not None and len(trades) > 0:
        trades, holding = _补充交易K线定位(trades, holding, result.get("原始K线数据"))
        trades.to_csv(os.path.join(stock_dir, "交易明细.csv"), index=False, encoding="utf-8-sig")
    if holding is not None and len(holding) > 0:
        holding.to_csv(os.path.join(stock_dir, "持仓过程.csv"), index=False, encoding="utf-8-sig")
    with open(os.path.join(stock_dir, "回测摘要.txt"), "w", encoding="utf-8") as target:
        target.write(f"股票代码: {result.get('股票代码', '')}\n")
        target.write(f"股票名称: {result.get('股票名称') or 获取股票名称(result.get('股票代码'))}\n")
        target.write(f"初始资金: {result.get('初始资金', 0):,.0f}\n")
        target.write(f"最终权益: {result.get('最终权益', 0):,.0f}\n")
        target.write(f"总收益率: {result.get('总收益率', 0):+.2f}%\n")
        target.write(f"最大回撤: {result.get('最大回撤', 0):.2f}%\n")
        target.write(f"胜率: {result.get('胜率', 0):.2f}%\n")
        target.write(f"交易次数: {result.get('买入次数', 0)}买 / {result.get('卖出次数', 0)}卖\n")
    return os.path.join(stock_dir, "策略决策回放.html")


def _保存多股回放数据(result, stock_dir):
    """保存按需生成个股回放所需的紧凑行情快照。

    多股回测不应在整理阶段为每只股票预生成几十 MB 的 HTML；只保存
    回放需要的行情列，页面首次打开时再生成对应 HTML。
    """
    data = result.get("原始K线数据")
    if data is None or len(data) == 0:
        return None
    columns = [
        "完整时间", "日期", "前复权_开盘", "前复权_最高", "前复权_最低",
        "前复权_收盘", "不复权_开盘", "不复权_最高", "不复权_最低",
        "不复权_收盘", "RSI_14", "RSI_最高价", "RSI_收盘价", "RSI_最低价",
        "RSI_均线_20", "ATR_14",
    ]
    snapshot = data[[col for col in columns if col in data.columns]].copy()
    path = os.path.join(stock_dir, "回放行情.csv.gz")
    snapshot.to_csv(path, index=False, compression="gzip", encoding="utf-8")
    return path


def 执行单股任务(task):
    # 第7项为多股本次运行的单票结果目录；单股模式不使用本函数。
    stock, config_dir, start, end, capital, liquidity_limit, stock_dir = (
        task + (None,) if len(task) == 6 else task
    )
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result = 跑回测(
                stock,
                开始日期=start,
                结束日期=end,
                初始资金=capital,
                配置目录=config_dir,
                运行参数={"流动性上限比例": liquidity_limit, "多股资金池模式": True},
                静默=True,
            )
        if result is None:
            return {"股票代码": stock, "股票名称": 获取股票名称(stock), "错误": "无可用回测结果"}
        result['初始资金'] = capital
        report_path = _保存多股单票结果(result, stock_dir) if stock_dir else None
        summary = 单股摘要(result, start, end)
        summary['初始资金'] = capital
        summary['结果目录'] = stock_dir
        summary['回放文件'] = report_path
        return summary
    except Exception as error:
        return {"股票代码": stock, "股票名称": 获取股票名称(stock), "错误": str(error)}


def 汇总结果(details):
    valid = [item for item in details if "错误" not in item]
    if not valid:
        return {"股票数": 0, "综合得分": -999.0}
    mean_annual = sum(item["年化收益率"] for item in valid) / len(valid)
    mean_drawdown = sum(item["最大回撤"] for item in valid) / len(valid)
    total_buys = sum(item["买入次数"] for item in valid)
    total_sells = sum(item["卖出次数"] for item in valid)
    # “总交易数”表示实际成交笔数（买入+卖出）；胜率仍以已完成卖出交易为分母。
    total_trades = total_buys + total_sells
    win_rate = (
        sum(item["胜率"] * item["卖出次数"] for item in valid) / total_sells
        if total_sells else 0.0
    )
    profit_loss_ratio = sum(item["盈亏比"] for item in valid) / len(valid)
    return_drawdown = mean_annual / max(mean_drawdown, 1e-6)
    score = 0.5 * return_drawdown + 0.3 * win_rate + 0.2 * profit_loss_ratio
    return {
        "股票数": len(valid),
        "买入总数": total_buys,
        "卖出总数": total_sells,
        "总交易数": total_trades,
        "平均年化收益率": mean_annual,
        "平均最大回撤": mean_drawdown,
        "加权胜率": win_rate,
        "平均盈亏比": profit_loss_ratio,
        "收益回撤比": return_drawdown,
        "综合得分": score,
    }


def main():
    parser = argparse.ArgumentParser(description="策略0717统一多股票回测")
    parser.add_argument("--config", default="1_策略配置", help="配置目录")
    parser.add_argument("--stocks", required=True, help="逗号分隔股票或列表文件")
    parser.add_argument("--start", required=True, help="开始日期")
    parser.add_argument("--end", required=True, help="结束日期")
    parser.add_argument("--capital", type=float, default=20_000_000)
    parser.add_argument("--liquidity-limit", type=float, default=0.01)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--portfolio-mode", choices=("shared", "independent"), default="shared",
        help="shared=统一交易核心+共享账户；independent=旧版独立账户对照",
    )
    parser.add_argument("--output", help="同时保存JSON文件")
    args = parser.parse_args()

    config_dir = os.path.abspath(args.config)
    stocks = 读取股票列表(args.stocks)
    if args.portfolio_mode == "shared":
        from 组合回测.统一多股执行器 import 运行共享账户回测
        with contextlib.redirect_stdout(io.StringIO()):
            shared = 运行共享账户回测(
                stocks, args.start, args.end, args.capital, config_dir,
                liquidity_limit=args.liquidity_limit,
            )
        details = [
            单股摘要(result, args.start, args.end)
            for result in shared["股票结果"]
        ] + shared.get("错误", [])
        account_snapshot = shared["账户"].快照()
        portfolio_curve = shared["组合权益曲线"]
    else:
        tasks = [
            (stock, config_dir, args.start, args.end, args.capital, args.liquidity_limit)
            for stock in stocks
        ]
        if args.workers > 1:
            with ProcessPoolExecutor(max_workers=args.workers) as executor:
                details = list(executor.map(执行单股任务, tasks))
        else:
            details = [执行单股任务(task) for task in tasks]
        account_snapshot = {}
        portfolio_curve = []

    module_manager = 模块开关管理器(config_dir)
    report = {
        "配置目录": config_dir,
        "模块开关": {
            "统计": module_manager.统计(),
            "已启用模块": [
                f"{item['类别']}.{item['标识']}"
                for item in module_manager.扁平清单()
                if item.get("启用")
            ],
        },
        "股票列表": stocks,
        "开始日期": args.start,
        "结束日期": args.end,
        "初始资金": args.capital,
        "流动性上限比例": args.liquidity_limit,
        "并行进程数": args.workers,
        "资金模式": "共享账户" if args.portfolio_mode == "shared" else "等额独立账户",
        "共享账户快照": account_snapshot,
        "组合权益曲线": portfolio_curve,
        "汇总": 汇总结果(details),
        "股票明细": details,
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    # 命令行入口与页面入口使用同一证据目录契约。
    if args.output:
        evidence_dir = os.path.splitext(os.path.abspath(args.output))[0] + "_运行"
    else:
        evidence_dir = os.path.join(
            项目根目录, "10_实验记录",
            "命令行回测_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"),
        )
    os.makedirs(evidence_dir, exist_ok=True)
    manifest = {
        "schema_version": "1.0", "run_id": os.path.basename(evidence_dir),
        "run_type": "CLI_BACKTEST", "status": "COMPLETED",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "start_date": args.start, "end_date": args.end, "stocks": stocks,
        "stock_count": len(stocks), "account_mode": report["资金模式"],
        "capital": args.capital, "config_dir": config_dir,
        "save_level": "STANDARD_AUDIT", "locked": False,
    }
    with open(os.path.join(evidence_dir, "运行清单.json"), "w", encoding="utf-8") as target:
        json.dump(manifest, target, ensure_ascii=False, indent=2)
    with open(os.path.join(evidence_dir, "回测结果.json"), "w", encoding="utf-8") as target:
        target.write(payload)
    # 保存交易证据，审计不依赖页面重新推算。
    trade_frames = []
    for item in (shared.get("股票结果", []) if args.portfolio_mode == "shared" else []):
        trades = item.get("交易明细")
        if trades is not None and len(trades):
            trade_frames.append(为交易证据添加股票范围编号(trades, item.get("股票代码", "")))
    if trade_frames:
        pd.concat(trade_frames, ignore_index=True).to_csv(
            os.path.join(evidence_dir, "交易明细.csv"), index=False
        )
    from 运行程序.可信度审计 import 审计运行目录
    credibility = 审计运行目录(evidence_dir)
    manifest["credibility_status"] = credibility["overall_status"]
    manifest["can_be_baseline"] = credibility["can_be_baseline"]
    with open(os.path.join(evidence_dir, "运行清单.json"), "w", encoding="utf-8") as target:
        json.dump(manifest, target, ensure_ascii=False, indent=2)
    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as target:
            target.write(payload)
    print(payload)


if __name__ == "__main__":
    main()
