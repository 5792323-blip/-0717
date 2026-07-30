#!/usr/bin/env python3
"""从百度股市通公开接口下载历史 PE(TTM)/PB 日值。"""

import argparse
import json
import time
from pathlib import Path

import pandas as pd


def 下载(stocks, output, delay=0.15):
    import akshare as ak
    rows, errors = [], []
    for i, stock in enumerate(dict.fromkeys(stocks), 1):
        code = "".join(ch for ch in str(stock) if ch.isdigit())[-6:]
        if len(code) != 6:
            continue
        try:
            pe = ak.stock_zh_valuation_baidu(code, "市盈率(TTM)", "全部")
            pb = ak.stock_zh_valuation_baidu(code, "市净率", "全部")
            pe = pe.rename(columns={"date": "实际披露日", "value": "PE_TTM"})
            pb = pb.rename(columns={"date": "实际披露日", "value": "PB_MRQ"})
            frame = pe.merge(pb, on="实际披露日", how="outer")
            frame.insert(0, "股票代码", code)
            frame["评分日期"] = frame["实际披露日"]
            frame["数据来源"] = "AKShare/百度股市通历史估值"
            frame["来源等级"] = "公开"
            rows.append(frame)
        except Exception as error:
            errors.append({"股票代码": code, "错误": f"{type(error).__name__}: {error}"})
        if delay:
            time.sleep(delay)
        if i % 20 == 0:
            print(f"已处理 {i}/{len(stocks)}")
    result = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if not result.empty:
        result["实际披露日"] = pd.to_datetime(result["实际披露日"], errors="coerce").dt.strftime("%Y-%m-%d")
        result = result.dropna(subset=["实际披露日"]).drop_duplicates(["股票代码", "实际披露日"])
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False, encoding="utf-8-sig")
    return {"输出": str(output), "记录数": len(result), "股票数": int(result["股票代码"].nunique()) if not result.empty else 0, "失败数": len(errors), "失败明细": errors}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stocks", default="数据模块/hs300_list.txt")
    parser.add_argument("--output", default="数据模块/历史估值_pe_pb.csv", type=Path)
    parser.add_argument("--delay", default=0.15, type=float)
    args = parser.parse_args()
    stocks = Path(args.stocks).read_text(encoding="utf-8-sig").splitlines()
    print(json.dumps(下载(stocks, args.output, args.delay), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
