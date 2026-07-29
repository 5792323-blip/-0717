#!/usr/bin/env python3
"""下载 2020-2026 个股历史基本面快照。

财务值来自公开财务摘要，实际披露日来自新浪财报公告日期。结果单独写入
历史文件，不覆盖当前研究快照；无法可靠取得的估值和治理字段保持为空。
"""

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from 基本面.下载当前个股基本面快照 import _latest_report, _num, _pick


DEFAULT_STOCKS = ROOT / "数据模块/hs300_list.txt"
DEFAULT_OUTPUT = ROOT / "数据模块/基本面历史快照_2020_2026.csv"
DEFAULT_REPORT = ROOT / "基本面/运行记录/历史个股基本面下载报告.json"
START_PERIOD = "20200331"
END_PERIOD = "20260630"


def _code(value):
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits[-6:] if len(digits) >= 6 else ""


def _announcement_map(stock):
    """返回报告期到最新公告日的映射。"""
    import akshare as ak

    prefix = "sh" if stock.startswith(("600", "601", "603", "605", "688")) else "sz"
    frame = ak.stock_financial_report_sina(stock=f"{prefix}{stock}")
    if frame is None or frame.empty:
        return {}
    data = frame.copy()
    data["报告日"] = data["报告日"].astype(str).str[:8]
    data["公告日期"] = pd.to_datetime(data.get("公告日期"), errors="coerce")
    data = data.dropna(subset=["公告日期"])
    data = data[(data["报告日"] >= START_PERIOD) & (data["报告日"] <= END_PERIOD)]
    if data.empty:
        return {}
    data = data.sort_values(["报告日", "公告日期"])
    return {
        row["报告日"]: {
            "实际披露日": row["公告日期"].strftime("%Y-%m-%d"),
            "审计意见": "未审计" if str(row.get("是否审计", "")) == "未审计" else str(row.get("是否审计", "")),
        }
        for _, row in data.groupby("报告日", as_index=False).tail(1).iterrows()
    }


def _analysis_map(stock):
    import akshare as ak

    frame = ak.stock_financial_analysis_indicator(symbol=stock, start_year="2020")
    if frame is None or frame.empty or "日期" not in frame.columns:
        return {}
    data = frame.copy()
    data["日期"] = pd.to_datetime(data["日期"], errors="coerce")
    data = data.dropna(subset=["日期"])
    result = {}
    for _, row in data.iterrows():
        period = row["日期"].strftime("%Y%m%d")
        debt = _num(row.get("长期负债比率(%)"))
        if debt is not None and abs(debt) > 1:
            debt /= 100
        result[period] = {
            "有息负债率": debt,
            "利息保障倍数": _num(row.get("利息支付倍数")),
            "应收周转天数": _num(row.get("应收账款周转天数(天)")),
            "存货周转天数": _num(row.get("存货周转天数(天)")),
        }
    return result


def _row(stock, period, abstract, announcements, analysis):
    report = announcements.get(period, {})
    disclosure = report.get("实际披露日", "")
    period_date = f"{period[:4]}-{period[4:6]}-{period[6:8]}"
    period_ts = pd.Timestamp(period_date)

    def pick(label):
        return _pick(abstract, label, period)

    revenue = pick("营业总收入")
    profit = pick("归母净利润")
    cashflow = pick("经营现金流量净额")
    fcf_per_share = pick("每股企业自由现金流量")
    shares = pick("摊薄每股净资产_期末股数")
    fcf = fcf_per_share * shares if fcf_per_share is not None and shares is not None else None
    roe, roic = pick("净资产收益率(ROE)"), pick("投入资本回报率")
    debt = pick("资产负债率")
    cfo_profit = pick("经营活动净现金/归属母公司的净利润")
    for key, value in (("roe", roe), ("roic", roic), ("debt", debt), ("cfo", cfo_profit)):
        if value is not None and abs(value) > 1:
            if key != "cfo" or abs(value) > 10:
                if key in ("roe", "roic", "debt") or abs(value) > 10:
                    value /= 100
        if key == "roe": roe = value
        elif key == "roic": roic = value
        elif key == "debt": debt = value
        else: cfo_profit = value
    prior = f"{int(period[:4]) - 3}{period[4:]}"
    revenue_prior = _pick(abstract, "营业总收入", prior)
    profit_deducted = pick("扣非净利润")
    profit_prior = _pick(abstract, "扣非净利润", prior)
    revenue_cagr = ((revenue / revenue_prior) ** (1 / 3) - 1
                    if revenue and revenue_prior and revenue > 0 and revenue_prior > 0 else None)
    profit_cagr = ((profit_deducted / profit_prior) ** (1 / 3) - 1
                   if profit_deducted and profit_prior and profit_deducted > 0 and profit_prior > 0 else None)
    analysis_row = analysis.get(period, {})
    return {
        "股票代码": stock, "报告期": period_date, "实际披露日": disclosure,
        "数据截止日": period_date, "评分日期": disclosure,
        "数据来源": "AKShare/东方财富财务摘要+新浪财报公告",
        "来源等级": "公开", "收入": revenue, "归母净利润": profit,
        "扣非净利润": profit_deducted, "经营现金流净额": cashflow,
        "自由现金流": fcf, "FCF净利比": fcf / profit if fcf is not None and profit not in (None, 0) else cfo_profit,
        "ROE": roe, "ROIC": roic, "收入3年CAGR": revenue_cagr,
        "扣非净利润3年CAGR": profit_cagr, "资产负债率": debt,
        "有息负债率": analysis_row.get("有息负债率"),
        "利息保障倍数": analysis_row.get("利息保障倍数"),
        "应收周转天数": analysis_row.get("应收周转天数") or pick("应收周转天数"),
        "存货周转天数": analysis_row.get("存货周转天数") or pick("存货周转天数"),
        "PE_TTM": None, "PB_MRQ": None, "EV_EBITDA": None, "FCF_Yield": None,
        "审计意见": report.get("审计意见", ""), "监管处罚次数": None,
        "大股东质押率": None, "商誉净资产比": None, "关联交易风险": "",
        "数据状态": "历史财务快照，估值与治理字段待补",
        "备注": "实际披露日缺失的报告期不得进入严格历史评分",
    }


def fetch_stock(stock):
    import akshare as ak

    abstract = ak.stock_financial_abstract(stock)
    periods = [p for p in abstract.columns if str(p).isdigit() and len(str(p)) == 8 and START_PERIOD <= str(p) <= END_PERIOD]
    announcements = _announcement_map(stock)
    analysis = _analysis_map(stock)
    return [_row(stock, str(period), abstract, announcements, analysis) for period in sorted(periods)]


def run(stocks, output, report_path, delay=0.15):
    unique = list(dict.fromkeys(_code(item) for item in stocks if _code(item)))
    rows, errors = [], []
    for index, stock in enumerate(unique, 1):
        try:
            rows.extend(fetch_stock(stock))
        except Exception as error:
            errors.append({"股票代码": stock, "错误": f"{type(error).__name__}: {error}"})
        if index % 10 == 0:
            print(f"已处理 {index}/{len(unique)}，记录 {len(rows)}，失败 {len(errors)}")
        if delay:
            time.sleep(delay)
    result = pd.DataFrame(rows)
    if not result.empty:
        # 同一公告日可能同时返回多个报告期，只保留最新报告期作为该日快照。
        result = result.sort_values(["股票代码", "实际披露日", "报告期"])
        result = result.drop_duplicates(["股票代码", "实际披露日"], keep="last")
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False, encoding="utf-8-sig")
    detail = {
        "运行日期": date.today().isoformat(), "目标股票数": len(unique),
        "成功股票数": int(result["股票代码"].nunique()) if not result.empty else 0,
        "记录数": len(result), "失败数": len(errors), "失败明细": errors,
        "输出": str(output), "范围": f"{START_PERIOD[:4]}-{START_PERIOD[4:6]} 至 {END_PERIOD[:4]}-{END_PERIOD[4:6]}",
        "说明": "历史财务数据；估值与治理字段缺失时不得伪造，不代表完整回测已就绪",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
    return detail


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stocks", default=str(DEFAULT_STOCKS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), type=Path)
    parser.add_argument("--report", default=str(DEFAULT_REPORT), type=Path)
    parser.add_argument("--delay", default=0.15, type=float)
    args = parser.parse_args()
    stocks = Path(args.stocks).read_text(encoding="utf-8-sig").splitlines()
    print(json.dumps(run(stocks, args.output, args.report, args.delay), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
