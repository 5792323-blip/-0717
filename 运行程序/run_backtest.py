#!/usr/bin/env python3
"""统一多股票回测入口，输出机器可读JSON。"""

import argparse
import contextlib
import io
import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import date

项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 项目根目录)

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


def _保存多股单票结果(result, stock_dir):
    """保存多股本次运行的单票完整证据，不改变单股保存流程。"""
    os.makedirs(stock_dir, exist_ok=True)
    trades = result.get("交易明细")
    holding = result.get("持仓过程")
    if trades is not None and len(trades) > 0:
        trades.to_csv(os.path.join(stock_dir, "交易明细.csv"), index=False, encoding="utf-8-sig")
    if holding is not None and len(holding) > 0:
        holding.to_csv(os.path.join(stock_dir, "持仓过程.csv"), index=False, encoding="utf-8-sig")
    with open(os.path.join(stock_dir, "回测摘要.txt"), "w", encoding="utf-8") as target:
        target.write(f"股票代码: {result.get('股票代码', '')}\n")
        target.write(f"初始资金: {result.get('初始资金', 0):,.0f}\n")
        target.write(f"最终权益: {result.get('最终权益', 0):,.0f}\n")
        target.write(f"总收益率: {result.get('总收益率', 0):+.2f}%\n")
        target.write(f"最大回撤: {result.get('最大回撤', 0):.2f}%\n")
        target.write(f"胜率: {result.get('胜率', 0):.2f}%\n")
        target.write(f"交易次数: {result.get('买入次数', 0)}买 / {result.get('卖出次数', 0)}卖\n")
    report_path = os.path.join(stock_dir, "策略决策回放.html")
    # 无成交股票不需要嵌入数万根K线，使用轻量诊断页避免多股回测产生数GB重复HTML。
    if trades is None or len(trades) == 0:
        with open(report_path, "w", encoding="utf-8") as target:
            target.write(
                "<!doctype html><meta charset='utf-8'><title>策略决策回放 - "
                f"{result.get('股票代码', '')}</title><style>body{{background:#101620;color:#d1d4dc;font-family:-apple-system,Microsoft YaHei,sans-serif;padding:28px}}h1{{color:#e94560}}.box{{background:#18202d;border:1px solid #334055;border-radius:8px;padding:18px;max-width:720px}}b{{color:#fff}}</style>"
                f"<h1>{result.get('股票代码', '')} 策略决策回放</h1><div class='box'>"
                f"<p>本次没有产生成交。</p><p>买入次数：<b>{result.get('买入次数', 0)}</b>　卖出次数：<b>{result.get('卖出次数', 0)}</b></p>"
                f"<p>初始资金：<b>{float(result.get('初始资金', 0)):,.2f}</b>　最终权益：<b>{float(result.get('最终权益', 0)):,.2f}</b></p>"
                "<p>详细原因请回到回测主页面的成交诊断，或使用有成交股票的完整K线回放。</p></div>"
            )
    else:
        from 回测引擎.report_generator import 生成报告
        生成报告(result, result.get("原始K线数据"), 输出路径=report_path)
    return report_path


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
            return {"股票代码": stock, "错误": "无可用回测结果"}
        result['初始资金'] = capital
        report_path = _保存多股单票结果(result, stock_dir) if stock_dir else None
        summary = 单股摘要(result, start, end)
        summary['初始资金'] = capital
        summary['结果目录'] = stock_dir
        summary['回放文件'] = report_path
        return summary
    except Exception as error:
        return {"股票代码": stock, "错误": str(error)}


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
    parser.add_argument("--output", help="同时保存JSON文件")
    args = parser.parse_args()

    config_dir = os.path.abspath(args.config)
    stocks = 读取股票列表(args.stocks)
    tasks = [
        (stock, config_dir, args.start, args.end, args.capital, args.liquidity_limit)
        for stock in stocks
    ]
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            details = list(executor.map(执行单股任务, tasks))
    else:
        details = [执行单股任务(task) for task in tasks]

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
        "汇总": 汇总结果(details),
        "股票明细": details,
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as target:
            target.write(payload)
    print(payload)


if __name__ == "__main__":
    main()
