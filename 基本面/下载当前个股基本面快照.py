#!/usr/bin/env python3
"""从 AKShare 公开接口抓取当前个股财务快照。

这是当前研究快照，不回填历史评分；每条记录保留最新财报公告日期。
"""

import argparse
import json
import time
from datetime import date
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STOCKS = ROOT / "数据模块/hs300_list.txt"
DEFAULT_OUTPUT = ROOT / "数据模块/基本面历史快照.csv"
REPORT_OUTPUT = ROOT / "基本面/运行记录/当前个股快照更新报告.json"


def _code(value):
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits[-6:] if len(digits) >= 6 else ""


def _num(value):
    try:
        value = float(value)
        return value if pd.notna(value) else None
    except (TypeError, ValueError):
        return None


def _pick(frame, label, period):
    rows = frame[frame["指标"].astype(str).str.strip() == label]
    if rows.empty or period not in rows.columns:
        return None
    return _num(rows.iloc[0][period])


def _latest_period(frame):
    periods = []
    for value in frame.columns:
        if str(value).isdigit() and len(str(value)) == 8:
            periods.append(str(value))
    return max(periods) if periods else None


def _latest_report(stock):
    import akshare as ak

    prefix = "sh" if stock.startswith(("600", "601", "603", "605", "688")) else "sz"
    frame = ak.stock_financial_report_sina(stock=f"{prefix}{stock}")
    if frame is None or frame.empty:
        return None
    frame = frame.copy()
    frame["公告日期"] = pd.to_datetime(frame.get("公告日期"), errors="coerce")
    frame = frame.dropna(subset=["公告日期"]).sort_values("公告日期")
    if frame.empty:
        return None
    row = frame.iloc[-1]
    return {
        "报告期": str(row.get("报告日", ""))[:10],
        "实际披露日": row["公告日期"].strftime("%Y-%m-%d"),
        "审计意见": "未审计" if str(row.get("是否审计", "")) == "未审计" else str(row.get("是否审计", "")),
    }


def _latest_analysis(stock):
    """读取公开财务分析表中最新一条可用报告，失败时返回空值。"""
    import akshare as ak

    frame = ak.stock_financial_analysis_indicator(symbol=stock, start_year="2020")
    if frame is None or frame.empty or "日期" not in frame.columns:
        return {}
    data = frame.copy()
    data["日期"] = pd.to_datetime(data["日期"], errors="coerce")
    data = data.dropna(subset=["日期"]).sort_values("日期")
    if data.empty:
        return {}
    row = data.iloc[-1]

    def pick(label):
        return _num(row.get(label))

    debt_ratio = pick("长期负债比率(%)")
    if debt_ratio is not None and abs(debt_ratio) > 1:
        debt_ratio /= 100
    return {
        "利息保障倍数": pick("利息支付倍数"),
        "有息负债率": debt_ratio,
        "应收周转天数": pick("应收账款周转天数(天)"),
        "存货周转天数": pick("存货周转天数(天)"),
    }


def _latest_valuation(stock):
    """读取当前公开估值序列；这类数据只代表当前快照，不回填历史。"""
    import akshare as ak

    values = {}
    for indicator, field in (("市盈率(TTM)", "PE_TTM"), ("市净率", "PB_MRQ"), ("总市值", "总市值")):
        try:
            frame = ak.stock_zh_valuation_baidu(symbol=stock, indicator=indicator, period="近一年")
            if frame is None or frame.empty:
                continue
            frame = frame.copy()
            frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
            frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
            frame = frame.dropna(subset=["date", "value"]).sort_values("date")
            if not frame.empty:
                values[field] = _num(frame.iloc[-1]["value"])
                values.setdefault("估值日期", frame.iloc[-1]["date"].strftime("%Y-%m-%d"))
        except Exception:
            # 公开接口不稳定时保留缺失，不能用估值中位数伪造数据。
            continue
    return values


def fetch_stock(stock, score_date):
    import akshare as ak

    abstract = ak.stock_financial_abstract(stock)
    period = _latest_period(abstract)
    if not period:
        raise ValueError("没有可用报告期")
    report = _latest_report(stock) or {
        "报告期": period,
        "实际披露日": "",
        "审计意见": "",
    }
    analysis = _latest_analysis(stock)
    valuation = _latest_valuation(stock)
    revenue = _pick(abstract, "营业总收入", period)
    net_profit = _pick(abstract, "归母净利润", period)
    cfo = _pick(abstract, "经营现金流量净额", period)
    fcf_per_share = _pick(abstract, "每股企业自由现金流量", period)
    net_assets = _pick(abstract, "股东权益合计(净资产)", period)
    latest_shares = _pick(abstract, "摊薄每股净资产_期末股数", period)
    capex = None
    if fcf_per_share is not None and latest_shares is not None:
        fcf = fcf_per_share * latest_shares
    else:
        fcf = None
    roe = _pick(abstract, "净资产收益率(ROE)", period)
    if roe is not None and abs(roe) > 1:
        roe /= 100
    debt = _pick(abstract, "资产负债率", period)
    if debt is not None and abs(debt) > 1:
        debt /= 100
    cfo_profit = _pick(abstract, "经营活动净现金/归属母公司的净利润", period)
    if cfo_profit is not None and abs(cfo_profit) > 10:
        cfo_profit /= 100
    prior_period = f"{int(period[:4]) - 3}{period[4:]}"
    revenue_prior = _pick(abstract, "营业总收入", prior_period)
    deducted_profit = _pick(abstract, "扣非净利润", period)
    deducted_prior = _pick(abstract, "扣非净利润", prior_period)
    revenue_cagr = (
        (revenue / revenue_prior) ** (1 / 3) - 1
        if revenue and revenue_prior and revenue > 0 and revenue_prior > 0 else None
    )
    profit_cagr = (
        (deducted_profit / deducted_prior) ** (1 / 3) - 1
        if deducted_profit and deducted_prior and deducted_profit > 0 and deducted_prior > 0 else None
    )
    roic = _pick(abstract, "投入资本回报率", period)
    if roic is not None and abs(roic) > 1:
        roic /= 100
    return {
        "股票代码": stock,
        "报告期": report["报告期"],
        "实际披露日": report["实际披露日"],
        "数据截止日": f"{period[:4]}-{period[4:6]}-{period[6:8]}",
        "评分日期": score_date,
        "数据来源": "AKShare/新浪财务报告+东方财富财务摘要",
        "来源等级": "公开",
        "收入": revenue,
        "归母净利润": net_profit,
        "扣非净利润": deducted_profit,
        "经营现金流净额": cfo,
        "自由现金流": fcf,
        "FCF净利比": (fcf / net_profit if fcf is not None and net_profit not in (None, 0) else cfo_profit),
        "ROE": roe,
        "ROIC": roic,
        "收入3年CAGR": revenue_cagr,
        "扣非净利润3年CAGR": profit_cagr,
        "资产负债率": debt,
        "应收周转天数": _pick(abstract, "应收账款周转天数", period),
        "存货周转天数": _pick(abstract, "存货周转天数", period),
        "有息负债率": analysis.get("有息负债率"),
        "利息保障倍数": analysis.get("利息保障倍数"),
        "PE_TTM": valuation.get("PE_TTM"),
        "PB_MRQ": valuation.get("PB_MRQ"),
        "估值日期": valuation.get("估值日期", ""),
        "估值数据状态": "当前估值快照，历史估值待核验" if valuation else "缺失",
        "毛利率": _pick(abstract, "毛利率", period),
        "净利率": _pick(abstract, "销售净利率", period),
        "审计意见": report["审计意见"],
        "数据状态": "当前快照，估值为当前市场数据" if valuation else "当前快照，估值缺失",
        "备注": "公开接口当前财务数据；当前估值不用于严格历史回测",
    }


def run(stocks, output, delay=0.15):
    score_date = date.today().isoformat()
    rows, errors = [], []
    unique_stocks = list(dict.fromkeys(_code(item) for item in stocks if _code(item)))
    for index, stock in enumerate(unique_stocks, 1):
        if not stock:
            continue
        try:
            rows.append(fetch_stock(stock, score_date))
        except Exception as error:
            errors.append({"股票代码": stock, "错误": f"{type(error).__name__}: {error}"})
        if delay:
            time.sleep(delay)
        if index % 20 == 0:
            print(f"已处理 {index}/{len(unique_stocks)}，成功 {len(rows)}，失败 {len(errors)}")
    result = pd.DataFrame(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False, encoding="utf-8-sig")
    report = {
        "运行日期": score_date, "目标股票数": len(unique_stocks),
        "成功数": len(result), "失败数": len(errors), "失败明细": errors,
        "输出": str(output), "说明": "当前快照，不得直接作为历史回测数据",
    }
    REPORT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stocks", default=str(DEFAULT_STOCKS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--delay", type=float, default=0.15)
    args = parser.parse_args()
    stocks = Path(args.stocks).read_text(encoding="utf-8-sig").splitlines()
    result = run(stocks, Path(args.output), args.delay)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
