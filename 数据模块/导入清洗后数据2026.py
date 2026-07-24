#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将桌面清洗后的60分钟数据合并到策略raw目录，保留现有2026年行情。"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from 策略引擎.atr import 计算ATR
from 策略引擎.rsi_source import 准备RSI指标


项目根目录 = Path(__file__).resolve().parents[1]
新数据目录 = Path.home() / "Desktop" / "清洗后数据2026"
原始数据目录 = 项目根目录 / "数据模块" / "raw"
历史截止日期 = pd.Timestamp("2025-12-31")


def 数值列(df, columns):
    for column in columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def 读取新数据(股票代码):
    qfq_path = 新数据目录 / "60min前复权" / f"{股票代码}_SZ.csv"
    market_path = 新数据目录 / "60min行情" / f"{股票代码}_SZ.csv"
    exchange = "SZ"
    if not qfq_path.exists() or not market_path.exists():
        qfq_path = 新数据目录 / "60min前复权" / f"{股票代码}_SH.csv"
        market_path = 新数据目录 / "60min行情" / f"{股票代码}_SH.csv"
        exchange = "SH"
    daily_path = 新数据目录 / "前复权日线" / f"{股票代码}_{exchange}.csv"
    if not all(path.exists() for path in (qfq_path, market_path, daily_path)):
        return None

    qfq = pd.read_csv(qfq_path, encoding="utf-8-sig")
    market = pd.read_csv(market_path, encoding="utf-8-sig")
    daily = pd.read_csv(daily_path, encoding="utf-8-sig")
    qfq["完整时间"] = pd.to_datetime(qfq["时间"], errors="coerce")
    market["完整时间"] = pd.to_datetime(market["时间"], errors="coerce")
    daily["日期"] = pd.to_datetime(daily["日期"], errors="coerce").dt.strftime("%Y-%m-%d")
    qfq = 数值列(qfq, ["开盘价", "最高价", "最低价", "收盘价"])
    market = 数值列(market, ["开盘价", "最高价", "最低价", "收盘价", "成交量", "成交额"])
    daily = 数值列(daily, ["成交量（股）", "成交额（元）", "换手率"])
    qfq = qfq.dropna(subset=["完整时间"]).drop_duplicates("完整时间").sort_values("完整时间")
    market = market.dropna(subset=["完整时间"]).drop_duplicates("完整时间").sort_values("完整时间")
    daily = daily.dropna(subset=["日期"]).drop_duplicates("日期").set_index("日期")
    if not qfq["完整时间"].equals(market["完整时间"]):
        raise ValueError(f"{股票代码} 前复权与不复权时间轴不一致")
    return 股票代码, exchange, qfq, market, daily


def 计算换手率(volume, dates, daily):
    volume = pd.to_numeric(volume, errors="coerce").fillna(0.0)
    dates = pd.Series(dates, index=volume.index).astype(str).str[:10]
    daily_total = dates.map(daily["成交量（股）"] if "成交量（股）" in daily else pd.Series(dtype=float))
    daily_turnover = dates.map(daily["换手率"] if "换手率" in daily else pd.Series(dtype=float))
    grouped = volume.groupby(dates).transform("sum")
    scale = 100.0
    valid = (daily_total > 0) & (grouped > 0)
    ratios = (daily_total[valid] / grouped[valid]).replace([np.inf, -np.inf], np.nan).dropna()
    if len(ratios) and abs(float(ratios.median()) - 1.0) < 0.2:
        scale = 1.0
    shares = volume * scale
    grouped_shares = shares.groupby(dates).transform("sum")
    result = (shares / grouped_shares.replace(0, np.nan) * daily_turnover).fillna(0.0)
    return result.astype(float), scale


def 构建历史数据(股票代码, exchange, qfq, market, daily):
    result = pd.DataFrame({
        "完整时间": qfq["完整时间"],
        "日期": qfq["完整时间"].dt.strftime("%Y-%m-%d"),
        "股票代码": f"{exchange}_{股票代码}",
        "前复权_开盘": qfq["开盘价"].to_numpy(),
        "前复权_最高": qfq["最高价"].to_numpy(),
        "前复权_最低": qfq["最低价"].to_numpy(),
        "前复权_收盘": qfq["收盘价"].to_numpy(),
        "不复权_开盘": market["开盘价"].to_numpy(),
        "不复权_最高": market["最高价"].to_numpy(),
        "不复权_最低": market["最低价"].to_numpy(),
        "不复权_收盘": market["收盘价"].to_numpy(),
        "成交量": market["成交量"].to_numpy(),
        "成交额": market["成交额"].to_numpy(),
    })
    result["不复权_成交量"] = result["成交量"]
    result["换手率"], volume_scale = 计算换手率(result["成交量"], result["日期"], daily)
    result["成交量"] = (pd.to_numeric(result["成交量"], errors="coerce") * volume_scale).round().astype("int64")
    result["不复权_成交量"] = result["成交量"].astype(float)
    result["成交额"] = pd.to_numeric(result["成交额"], errors="coerce").round().astype("int64")
    result["异常标记"] = ""
    close_return = result["前复权_收盘"].pct_change()
    result.loc[close_return.abs() > 0.20, "异常标记"] = "涨跌幅异常>20%"
    return result, volume_scale


def 读取现有2026(股票代码):
    path = 原始数据目录 / f"{股票代码}_双价格合并.pkl"
    if not path.exists():
        return None
    current = pd.read_pickle(path).reset_index()
    if "完整时间" not in current:
        current["完整时间"] = pd.to_datetime(current["日期"], errors="coerce")
    else:
        current["完整时间"] = pd.to_datetime(current["完整时间"], errors="coerce")
    current["日期"] = current["完整时间"].dt.strftime("%Y-%m-%d")
    return current[current["完整时间"] > 历史截止日期].copy()


def 完成指标(df):
    df = df.sort_values("完整时间").drop_duplicates("完整时间").reset_index(drop=True)
    df = 准备RSI指标(df, 价格源="close", RSI周期=14, 均线周期=20)
    df["ATR_14"] = 计算ATR(df["前复权_最高"], df["前复权_最低"], df["前复权_收盘"], 周期=14)
    df.index = pd.to_datetime(df.pop("完整时间"))
    df.index.name = "完整时间"
    columns = [
        "日期", "股票代码", "前复权_开盘", "前复权_最高", "前复权_最低", "前复权_收盘",
        "成交量", "成交额", "换手率", "RSI_14", "RSI_均线_20", "ATR_14", "异常标记",
        "不复权_开盘", "不复权_最高", "不复权_最低", "不复权_收盘", "不复权_成交量",
    ]
    for column in columns:
        if column not in df:
            df[column] = np.nan
    return df[columns]


def 转换一只(股票代码):
    loaded = 读取新数据(股票代码)
    if loaded is None:
        return None
    code, exchange, qfq, market, daily = loaded
    history, volume_scale = 构建历史数据(code, exchange, qfq, market, daily)
    current = 读取现有2026(code)
    if current is not None and len(current):
        if "换手率" not in current:
            current["换手率"] = np.nan
        current["换手率"], _ = 计算换手率(current["成交量"], current["日期"], daily)
        combined = pd.concat([history[history["完整时间"] <= 历史截止日期], current], ignore_index=True)
    else:
        combined = history
    return 完成指标(combined), volume_scale


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--codes", nargs="*")
    args = parser.parse_args()
    qfq_files = sorted((新数据目录 / "60min前复权").glob("*.csv"))
    codes = args.codes or [path.stem.rsplit("_", 1)[0] for path in qfq_files]
    converted = {}
    failures = {}
    for code in codes:
        try:
            result = 转换一只(code)
            if result is None:
                failures[code] = "缺少前复权、不复权或日线文件"
                continue
            df, scale = result
            if len(df) < 100 or df.index.duplicated().any() or df[["前复权_收盘", "不复权_收盘"]].isna().any().any():
                failures[code] = "转换后校验失败"
                continue
            converted[code] = {"df": df, "scale": scale}
        except Exception as exc:
            failures[code] = repr(exc)
    print(json.dumps({"待处理": len(codes), "可替换": len(converted), "失败": len(failures), "失败示例": dict(list(failures.items())[:10])}, ensure_ascii=False, indent=2))
    if args.dry_run:
        return 0 if not failures else 1
    backup = 原始数据目录.parent / f"raw_backup_before_20260724_{pd.Timestamp.now().strftime('%H%M%S')}"
    backup.mkdir(parents=True, exist_ok=False)
    for code, item in converted.items():
        old_path = 原始数据目录 / f"{code}_双价格合并.pkl"
        if old_path.exists():
            shutil.copy2(old_path, backup / old_path.name)
        fd, temp_name = tempfile.mkstemp(prefix=f"{code}_", suffix=".pkl", dir=原始数据目录)
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            item["df"].to_pickle(temp_path)
            os.replace(temp_path, old_path)
        finally:
            temp_path.unlink(missing_ok=True)
    with open(backup / "转换记录.json", "w", encoding="utf-8") as target:
        json.dump({"converted": list(converted), "failures": failures}, target, ensure_ascii=False, indent=2)
    print(f"已写入 {len(converted)} 个双价格合并文件，备份目录：{backup}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
