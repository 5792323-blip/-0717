#!/usr/bin/env python3
"""横截面因子共享资金训练基线；只使用2020-2023。"""

import argparse
import json
import os
from datetime import datetime

import pandas as pd

from 运行程序.run_backtest import 读取股票列表
from 组合回测.横截面组合 import 因子列表, 加载面板, 读取交易成本, 运行组合


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def 精简(result):
    return {key: value for key, value in result.items() if key not in ("权益曲线", "交易明细")}


def 评价(full_result, bucket_results):
    yearly = full_result["年度"]
    positive_years = sum(item["收益率"] > 0 for item in yearly.values())
    cells = [item["收益率"] for result in bucket_results for item in result["年度"].values()]
    positive_cells = sum(value > 0 for value in cells)
    minimum_year = min(item["收益率"] for item in yearly.values())
    constraints = {
        "四个年度全部正收益": positive_years == 4,
        "十二个分桶年度至少九个正收益": positive_cells >= 9,
        "全期收益为正": full_result["总收益率"] > 0,
        "最大回撤不超过20%": full_result["最大回撤"] <= 0.20,
    }
    score = (
        0.45 * full_result["收益回撤比"]
        + 0.25 * minimum_year
        + 0.20 * (positive_cells / max(len(cells), 1))
        - 0.10 * full_result["累计双边换手"] / max(full_result["调仓次数"], 1)
    )
    return {
        "合格": all(constraints.values()),
        "硬约束": constraints,
        "正收益年度数": positive_years,
        "正收益分桶年度数": positive_cells,
        "分桶年度总数": len(cells),
        "最差年度收益": minimum_year,
        "横截面得分": score,
    }


def 沪深300基准(start, end, capital, target_gross=0.80):
    path = os.path.join(项目根目录, "数据模块", "大盘数据", "hs300_日K线.pkl")
    data = pd.read_pickle(path).copy()
    data["date"] = pd.to_datetime(data["date"])
    data = data[(data["date"] >= start) & (data["date"] <= end)].sort_values("date")
    normalized = data["close"].astype(float) / float(data["close"].iloc[0])
    equity = capital * ((1 - target_gross) + target_gross * normalized)
    curve = pd.DataFrame({"权益": equity.values}, index=data["date"])
    total_return = curve["权益"].iloc[-1] / capital - 1
    years = max((curve.index[-1] - curve.index[0]).days / 365.25, 1 / 252)
    annual_return = (1 + total_return) ** (1 / years) - 1
    drawdown = ((curve["权益"].cummax() - curve["权益"]) / curve["权益"].cummax()).max()
    yearly = {}
    for year, frame in curve.groupby(curve.index.year):
        yearly[str(year)] = {
            "收益率": float(frame["权益"].iloc[-1] / frame["权益"].iloc[0] - 1),
            "最大回撤": float(((frame["权益"].cummax() - frame["权益"]) / frame["权益"].cummax()).max()),
        }
    return {
        "总收益率": float(total_return), "年化收益率": float(annual_return),
        "最大回撤": float(drawdown), "收益回撤比": float(annual_return / max(drawdown, 1e-9)),
        "年度": yearly, "权益曲线": curve,
    }
def main():
    parser = argparse.ArgumentParser(description="横截面共享资金基线")
    parser.add_argument("--stocks", default="数据模块/hs300_prescreen_30.txt")
    parser.add_argument("--config", default="1_策略配置")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--capital", type=float, default=20_000_000)
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    if args.end >= "2024-01-01":
        raise ValueError("横截面训练结束日期必须早于封存验证期2024-01-01")
    output_dir = args.output_dir or os.path.join(
        项目根目录, "10_实验记录",
        f"横截面组合训练基线_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )
    os.makedirs(output_dir, exist_ok=True)
    stocks = 读取股票列表(args.stocks)
    daily = 加载面板(stocks, args.start, args.end)
    available = [stock for stock in stocks if stock in daily]
    buckets = [[stock for index, stock in enumerate(available) if index % 3 == bucket] for bucket in range(3)]
    costs = 读取交易成本(os.path.abspath(args.config))

    report = {
        "训练期": [args.start, args.end], "封存验证期": "未读取",
        "股票池": args.stocks, "可用股票数": len(available), "交易成本": costs,
        "固定设置": {"调仓频率": "每5个交易日", "目标总仓位": 0.8, "全池TopK": 5, "分桶TopK": 3},
        "因子": {},
    }
    equal_weight = 运行组合(
        daily, available, "20日动量", args.start, args.end, costs,
        args.capital, len(available), 0.80, 5,
    )
    hs300 = 沪深300基准(args.start, args.end, args.capital)
    equal_weight["权益曲线"].to_csv(os.path.join(output_dir, "股票池等权权益曲线.csv"), encoding="utf-8-sig")
    hs300["权益曲线"].to_csv(os.path.join(output_dir, "沪深300权益曲线.csv"), encoding="utf-8-sig")
    report["基准"] = {
        "股票池等权80%仓位": 精简(equal_weight),
        "沪深300_80%仓位": {key: value for key, value in hs300.items() if key != "权益曲线"},
    }
    for factor in 因子列表:
        factor_dir = os.path.join(output_dir, factor)
        os.makedirs(factor_dir, exist_ok=True)
        full = 运行组合(daily, available, factor, args.start, args.end, costs, args.capital, 5)
        full["权益曲线"].to_csv(os.path.join(factor_dir, "全池权益曲线.csv"), encoding="utf-8-sig")
        full["交易明细"].to_csv(os.path.join(factor_dir, "全池交易明细.csv"), index=False, encoding="utf-8-sig")
        bucket_results = []
        for index, bucket in enumerate(buckets, 1):
            result = 运行组合(daily, bucket, factor, args.start, args.end, costs, args.capital, 3)
            result["权益曲线"].to_csv(os.path.join(factor_dir, f"股票桶{index}_权益曲线.csv"), encoding="utf-8-sig")
            bucket_results.append(result)
        report["因子"][factor] = {
            "全池": 精简(full),
            "股票桶": [精简(result) for result in bucket_results],
            "评价": 评价(full, bucket_results),
            "相对股票池等权超额": full["总收益率"] - equal_weight["总收益率"],
            "相对沪深300超额": full["总收益率"] - hs300["总收益率"],
        }

    ranked = sorted(
        report["因子"],
        key=lambda name: (
            int(report["因子"][name]["评价"]["合格"]),
            report["因子"][name]["评价"]["正收益年度数"],
            report["因子"][name]["评价"]["正收益分桶年度数"],
            report["因子"][name]["评价"]["横截面得分"],
        ),
        reverse=True,
    )
    report["排名"] = ranked
    report["合格因子"] = [name for name in ranked if report["因子"][name]["评价"]["合格"]]
    with open(os.path.join(output_dir, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(report, target, ensure_ascii=False, indent=2)
    with open(os.path.join(output_dir, "中文报告.md"), "w", encoding="utf-8") as target:
        target.write("# 横截面共享资金组合训练基线\n\n")
        target.write(f"- 训练期：{args.start}至{args.end}；封存验证未读取。\n")
        target.write(f"- 股票数：{len(available)}；每5日调仓；80%目标仓位；全池Top5。\n\n")
        target.write(
            f"- 股票池等权基准：总收益{equal_weight['总收益率']:.2%}，最大回撤{equal_weight['最大回撤']:.2%}。\n"
            f"- 沪深300（80%仓位）基准：总收益{hs300['总收益率']:.2%}，最大回撤{hs300['最大回撤']:.2%}。\n\n"
        )
        target.write("|排名|因子|合格|总收益|对等权超额|对沪深300超额|最大回撤|正收益年度|正收益分桶|最差年度|双边换手|\n")
        target.write("|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for index, name in enumerate(ranked, 1):
            full = report["因子"][name]["全池"]
            evaluation = report["因子"][name]["评价"]
            target.write(
                f"|{index}|{name}|{'是' if evaluation['合格'] else '否'}|{full['总收益率']:.2%}|"
                f"{report['因子'][name]['相对股票池等权超额']:+.2%}|"
                f"{report['因子'][name]['相对沪深300超额']:+.2%}|{full['最大回撤']:.2%}|"
                f"{evaluation['正收益年度数']}/4|{evaluation['正收益分桶年度数']}/12|"
                f"{evaluation['最差年度收益']:.2%}|{full['累计双边换手']:.1f}x|\n"
            )
        target.write("\n")
        if report["合格因子"]:
            target.write(f"合格因子：{', '.join(report['合格因子'])}。\n")
        else:
            target.write("没有因子通过全部硬约束，不进入封存验证。\n")
    print(json.dumps({"输出目录": output_dir, "排名": ranked, "合格因子": report["合格因子"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
