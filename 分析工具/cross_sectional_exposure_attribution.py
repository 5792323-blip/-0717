#!/usr/bin/env python3
"""20日反转Top5的训练期风险暴露归因；不读取封存验证期。"""

import argparse
import json
import math
import os
from datetime import datetime

import numpy as np
import pandas as pd

from 运行程序.run_backtest import 读取股票列表
from 组合回测.横截面组合 import 加载面板, 构建矩阵, 横截面分数


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
暴露列 = ["beta_60", "volatility_20", "liquidity_20"]
板块列 = ["沪市主板", "深市主板", "创业板", "科创板", "北交所"]
主回撤开始 = pd.Timestamp("2021-12-23")
主回撤结束 = pd.Timestamp("2022-04-26")


def 计算滚动贝塔(stock_returns, market_returns, window=60, min_periods=40):
    aligned_market = market_returns.reindex(stock_returns.index)
    covariance = stock_returns.rolling(window, min_periods=min_periods).cov(aligned_market)
    variance = aligned_market.rolling(window, min_periods=min_periods).var(ddof=1)
    return (covariance / variance.where(variance > 0)).replace([np.inf, -np.inf], np.nan)


def 股票板块(stock):
    code = str(stock).zfill(6)
    if code.startswith(("688", "689")):
        return "科创板"
    if code.startswith(("300", "301")):
        return "创业板"
    if code.startswith(("8", "9")):
        return "北交所"
    if code.startswith("6"):
        return "沪市主板"
    return "深市主板"


def 加入暴露(daily_by_stock, market_close):
    market_returns = market_close.pct_change(fill_method=None)
    enriched = {}
    for stock, daily in daily_by_stock.items():
        frame = daily.copy()
        returns = frame["close"].pct_change(fill_method=None)
        frame["beta_60"] = 计算滚动贝塔(returns, market_returns)
        frame["volatility_20"] = returns.rolling(20, min_periods=20).std(ddof=0)
        enriched[stock] = frame
    return enriched


def 加载市场收盘(end):
    path = os.path.join(项目根目录, "数据模块", "大盘数据", "hs300_日K线.pkl")
    data = pd.read_pickle(path).copy()
    data["date"] = pd.to_datetime(data["date"])
    data = data[data["date"] <= pd.Timestamp(end)].sort_values("date").set_index("date")
    return data["close"].astype(float)


def 安全相关(x, y):
    frame = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(frame) < 3 or frame["x"].std(ddof=0) == 0 or frame["y"].std(ddof=0) == 0:
        return None
    return float(frame["x"].corr(frame["y"]))


def 残差化(score, exposures):
    frame = pd.concat([score.rename("score"), exposures], axis=1).dropna()
    if len(frame) <= exposures.shape[1] + 1:
        return pd.Series(dtype=float)
    design = np.column_stack([np.ones(len(frame)), frame[exposures.columns].to_numpy(dtype=float)])
    coefficients, _, _, _ = np.linalg.lstsq(design, frame["score"].to_numpy(dtype=float), rcond=None)
    residual = frame["score"].to_numpy(dtype=float) - design @ coefficients
    return pd.Series(residual, index=frame.index)


def 分组标签(rank):
    if rank <= 1 / 3:
        return "低"
    if rank <= 2 / 3:
        return "中"
    return "高"


def 构建归因样本(daily_by_stock, start, end, top_k=5, rebalance_every=5):
    universe = list(daily_by_stock)
    calendar = sorted(set().union(*(daily_by_stock[stock].index for stock in universe)))
    calendar = pd.DatetimeIndex([date for date in calendar if pd.Timestamp(start) <= date <= pd.Timestamp(end)])
    columns = ["open", "momentum_20", "reversal_5", "low_volatility_20", "liquidity_20", *暴露列]
    matrices = {column: 构建矩阵(daily_by_stock, column, calendar) for column in dict.fromkeys(columns)}
    open_prices = matrices["open"]
    periods = []
    positions = []
    for index in range(1, len(calendar)):
        if index % rebalance_every != 0 or index + rebalance_every >= len(calendar):
            continue
        signal_date = calendar[index - 1]
        trade_date = calendar[index]
        exit_date = calendar[index + rebalance_every]
        scores = 横截面分数(matrices, signal_date, universe, "20日反转").dropna()
        entry = open_prices.loc[trade_date].replace([np.inf, -np.inf], np.nan).dropna()
        exit_prices = open_prices.loc[exit_date].replace([np.inf, -np.inf], np.nan).dropna()
        tradable = scores.index.intersection(entry[entry > 0].index).intersection(exit_prices[exit_prices > 0].index)
        scores = scores.loc[tradable]
        exposure_frame = pd.DataFrame({
            column: matrices[column].loc[signal_date, tradable] for column in 暴露列
        }).replace([np.inf, -np.inf], np.nan)
        valid = exposure_frame.dropna().index
        scores = scores.loc[scores.index.intersection(valid)]
        if len(scores) < max(20, top_k):
            continue
        selected = scores.sort_values(ascending=False).head(top_k).index
        ranks = exposure_frame.loc[scores.index].rank(pct=True)
        stock_returns = exit_prices.loc[selected] / entry.loc[selected] - 1
        period = {
            "signal_date": signal_date, "trade_date": trade_date, "exit_date": exit_date,
            "gross_return": float(stock_returns.mean()),
            "selected_count": len(selected),
        }
        for column in 暴露列:
            period[f"{column}_rank"] = float(ranks.loc[selected, column].mean())
            period[f"{column}_raw"] = float(exposure_frame.loc[selected, column].mean())
        boards = pd.Series([股票板块(stock) for stock in selected]).value_counts(normalize=True)
        universe_boards = pd.Series([股票板块(stock) for stock in scores.index]).value_counts(normalize=True)
        period["board_max_share"] = float(boards.max())
        period["board_hhi"] = float((boards ** 2).sum())
        board_active_values = []
        for board in 板块列:
            active = float(boards.get(board, 0.0) - universe_boards.get(board, 0.0))
            period[f"board_active_{board}"] = active
            board_active_values.append(abs(active))
        period["board_max_active_abs"] = max(board_active_values)
        period["selected"] = ",".join(selected)
        periods.append(period)

        for stock in selected:
            row = {
                "signal_date": signal_date, "trade_date": trade_date, "exit_date": exit_date,
                "stock": stock, "board": 股票板块(stock), "forward_return": float(stock_returns.loc[stock]),
            }
            for column in 暴露列:
                rank = float(ranks.loc[stock, column])
                row[f"{column}_rank"] = rank
                row[f"{column}_group"] = 分组标签(rank)
            positions.append(row)
    return pd.DataFrame(periods), pd.DataFrame(positions)


def 暴露汇总(periods):
    result = {}
    masks = {
        "全期": pd.Series(True, index=periods.index),
        "主回撤区间": periods["trade_date"].between(主回撤开始, 主回撤结束),
        "非主回撤区间": ~periods["trade_date"].between(主回撤开始, 主回撤结束),
    }
    for year in sorted(periods["trade_date"].dt.year.unique()):
        masks[str(year)] = periods["trade_date"].dt.year == year
    for name, mask in masks.items():
        frame = periods.loc[mask]
        if frame.empty:
            continue
        result[name] = {
            "期数": len(frame), "平均持有期收益": float(frame["gross_return"].mean()),
            "正收益期占比": float((frame["gross_return"] > 0).mean()),
            "平均Beta百分位": float(frame["beta_60_rank"].mean()),
            "平均波动率百分位": float(frame["volatility_20_rank"].mean()),
            "平均流动性百分位": float(frame["liquidity_20_rank"].mean()),
            "平均原始Beta": float(frame["beta_60_raw"].mean()),
            "平均板块最大占比": float(frame["board_max_share"].mean()),
            "平均板块HHI": float(frame["board_hhi"].mean()),
        }
    return result


def 分组收益(positions):
    output = {}
    drawdown_mask = positions["trade_date"].between(主回撤开始, 主回撤结束)
    for column in 暴露列:
        output[column] = {}
        for group, frame in positions.groupby(f"{column}_group"):
            drawdown = frame.loc[drawdown_mask.reindex(frame.index, fill_value=False)]
            output[column][group] = {
                "样本数": len(frame), "全期平均收益": float(frame["forward_return"].mean()),
                "全期胜率": float((frame["forward_return"] > 0).mean()),
                "主回撤样本数": len(drawdown),
                "主回撤平均收益": float(drawdown["forward_return"].mean()) if len(drawdown) else None,
            }
    return output


def 年度分组收益(positions):
    output = {}
    for column in 暴露列:
        output[column] = {}
        for (year, group), frame in positions.groupby([positions["trade_date"].dt.year, f"{column}_group"]):
            output[column].setdefault(str(year), {})[group] = {
                "样本数": len(frame), "平均收益": float(frame["forward_return"].mean())
            }
    return output


def 板块主动暴露汇总(periods):
    masks = {
        "全期": pd.Series(True, index=periods.index),
        "主回撤区间": periods["trade_date"].between(主回撤开始, 主回撤结束),
        "非主回撤区间": ~periods["trade_date"].between(主回撤开始, 主回撤结束),
    }
    output = {}
    for name, mask in masks.items():
        frame = periods.loc[mask]
        output[name] = {
            board: float(frame[f"board_active_{board}"].mean()) for board in 板块列
        }
        output[name]["平均最大绝对主动权重"] = float(frame["board_max_active_abs"].mean())
    return output


def 板块收益汇总(positions):
    output = {}
    masks = {
        "全期": pd.Series(True, index=positions.index),
        "主回撤区间": positions["trade_date"].between(主回撤开始, 主回撤结束),
    }
    for name, mask in masks.items():
        output[name] = {}
        for board, frame in positions.loc[mask].groupby("board"):
            output[name][board] = {
                "样本数": len(frame), "平均收益": float(frame["forward_return"].mean()),
                "胜率": float((frame["forward_return"] > 0).mean()),
            }
    return output


def 相关归因(periods):
    return {
        "Beta百分位与收益": 安全相关(periods["beta_60_rank"], periods["gross_return"]),
        "波动率百分位与收益": 安全相关(periods["volatility_20_rank"], periods["gross_return"]),
        "流动性百分位与收益": 安全相关(periods["liquidity_20_rank"], periods["gross_return"]),
        "板块集中度与收益": 安全相关(periods["board_hhi"], periods["gross_return"]),
    }


def 中性化ic诊断(daily_by_stock, start, end):
    frames = []
    for stock, daily in daily_by_stock.items():
        frame = daily[["momentum_20", *暴露列]].copy()
        frame["forward_5"] = daily["close"].shift(-5) / daily["open"].shift(-1) - 1
        frame["stock"] = stock
        frames.append(frame.reset_index().rename(columns={"交易日": "date", "index": "date"}))
    panel = pd.concat(frames, ignore_index=True).replace([np.inf, -np.inf], np.nan)
    panel["date"] = pd.to_datetime(panel["date"])
    panel = panel[panel["date"].between(pd.Timestamp(start), pd.Timestamp(end))]
    records = []
    for date, group in panel.groupby("date"):
        data = group[["momentum_20", *暴露列, "forward_5"]].dropna()
        if len(data) < 50:
            continue
        raw_score = 1.0 - data["momentum_20"].rank(pct=True)
        exposure_ranks = data[暴露列].rank(pct=True)
        residual_score = 残差化(raw_score, exposure_ranks)
        common = residual_score.index.intersection(data.index)
        raw_ic = raw_score.loc[common].corr(data.loc[common, "forward_5"], method="spearman")
        residual_ic = residual_score.loc[common].corr(data.loc[common, "forward_5"], method="spearman")
        if math.isfinite(raw_ic) and math.isfinite(residual_ic):
            records.append({"date": date, "raw_ic": raw_ic, "residual_ic": residual_ic})
    result = {}
    frame = pd.DataFrame(records)
    for year, rows in frame.groupby(frame["date"].dt.year):
        result[str(year)] = {
            "日数": len(rows), "原始平均IC": float(rows["raw_ic"].mean()),
            "中性化平均IC": float(rows["residual_ic"].mean()),
            "IC变化": float(rows["residual_ic"].mean() - rows["raw_ic"].mean()),
            "中性化IC正值比例": float((rows["residual_ic"] > 0).mean()),
        }
    result["四年平均"] = {
        "原始平均IC": float(frame["raw_ic"].mean()),
        "中性化平均IC": float(frame["residual_ic"].mean()),
        "IC变化": float(frame["residual_ic"].mean() - frame["raw_ic"].mean()),
    }
    return result


def main():
    parser = argparse.ArgumentParser(description="20日反转风险暴露归因")
    parser.add_argument("--stocks", default="数据模块/hs300_list.txt")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    if args.end >= "2024-01-01":
        raise ValueError("归因结束日期必须早于封存验证期2024-01-01")
    output_dir = args.output_dir or os.path.join(
        项目根目录, "10_实验记录", f"横截面风险暴露归因_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )
    os.makedirs(output_dir, exist_ok=True)
    stocks = 读取股票列表(args.stocks)
    daily = 加载面板(stocks, args.start, args.end)
    daily = 加入暴露(daily, 加载市场收盘(args.end))
    periods, positions = 构建归因样本(daily, args.start, args.end)
    periods.to_csv(os.path.join(output_dir, "调仓期暴露.csv"), index=False, encoding="utf-8-sig")
    positions.to_csv(os.path.join(output_dir, "持仓暴露明细.csv"), index=False, encoding="utf-8-sig")
    report = {
        "训练期": [args.start, args.end], "封存验证期": "未读取", "股票数": len(daily),
        "时序": "t日收盘暴露，t+1开盘进入，下次调仓日开盘退出",
        "可用暴露": ["60日Beta", "20日波动率", "20日平均成交额流动性", "交易所板块"],
        "不可用暴露": {"行业": "本地无历史时点行业数据", "市值": "本地无历史总股本或市值数据"},
        "暴露汇总": 暴露汇总(periods),
        "收益相关": 相关归因(periods),
        "暴露分组收益": 分组收益(positions),
        "年度暴露分组收益": 年度分组收益(positions),
        "中性化IC诊断": 中性化ic诊断(daily, args.start, args.end),
        "板块主动暴露": 板块主动暴露汇总(periods),
        "板块持仓收益": 板块收益汇总(positions),
    }
    with open(os.path.join(output_dir, "结果.json"), "w", encoding="utf-8") as target:
        json.dump(report, target, ensure_ascii=False, indent=2)
    with open(os.path.join(output_dir, "中文报告.md"), "w", encoding="utf-8") as target:
        target.write("# 20日反转风险暴露归因\n\n")
        target.write("- 仅使用2020-2023训练期；封存验证未读取。\n")
        target.write("- 暴露在信号日收盘计算，下一日开盘进入，不使用未来数据。\n")
        target.write("- 行业与历史市值本地数据不可用，本报告不做静态回填。\n\n")
        target.write("|区间|期数|平均收益|Beta分位|波动分位|流动性分位|原始Beta|板块最大占比|\n")
        target.write("|---|---:|---:|---:|---:|---:|---:|---:|\n")
        for name, item in report["暴露汇总"].items():
            target.write(
                f"|{name}|{item['期数']}|{item['平均持有期收益']:.3%}|{item['平均Beta百分位']:.3f}|"
                f"{item['平均波动率百分位']:.3f}|{item['平均流动性百分位']:.3f}|"
                f"{item['平均原始Beta']:.3f}|{item['平均板块最大占比']:.1%}|\n"
            )
        target.write("\n## 暴露与持有期收益相关\n\n")
        for name, value in report["收益相关"].items():
            target.write(f"- {name}：{value:.4f}\n" if value is not None else f"- {name}：样本不足\n")
        target.write("\n## 板块主动暴露\n\n")
        target.write("|区间|沪市主板|深市主板|创业板|科创板|最大绝对主动权重|\n")
        target.write("|---|---:|---:|---:|---:|---:|\n")
        for name, item in report["板块主动暴露"].items():
            target.write(
                f"|{name}|{item['沪市主板']:+.1%}|{item['深市主板']:+.1%}|{item['创业板']:+.1%}|"
                f"{item['科创板']:+.1%}|{item['平均最大绝对主动权重']:.1%}|\n"
            )
        target.write("\n## Beta、波动率与流动性残差化IC\n\n")
        target.write("|年度|原始IC|中性化IC|变化|\n")
        target.write("|---|---:|---:|---:|\n")
        for name, item in report["中性化IC诊断"].items():
            target.write(
                f"|{name}|{item['原始平均IC']:.4f}|{item['中性化平均IC']:.4f}|{item['IC变化']:+.4f}|\n"
            )
    print(json.dumps({"输出目录": output_dir, "暴露汇总": report["暴露汇总"], "收益相关": report["收益相关"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
