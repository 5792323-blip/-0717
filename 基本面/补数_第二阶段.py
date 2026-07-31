#!/usr/bin/env python3
"""基本面补数第二阶段 — 使用同花顺报表计算 EV_EBITDA 等高阶指标。

数据源：
- stock_financial_debt_ths: 资产负债表（资产合计/负债合计/货币资金/商誉）
- stock_financial_benefit_ths: 利润表（利润总额/财务费用/利息费用）

补入字段：
1. EV_EBITDA = 企业价值 / EBITDA
2. 有息负债率（资产负债表：短期借款+长期借款+应付债券 / 总资产）
3. 利息保障倍数（利润表备选计算）
4. 商誉净资产比（零商誉 → 0）
5. 大股东质押率（匹配优化）

输出：更新后的快照 + 补数报告
"""

import json
import pickle
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_CURRENT = ROOT / "数据模块/基本面历史快照.csv"
SNAPSHOT_HISTORICAL = ROOT / "数据模块/基本面历史快照_2020_2026.csv"
STOCKS_FILE = ROOT / "数据模块/hs300_list.txt"
REPORT_DIR = ROOT / "基本面/运行记录"
CACHE_DIR = ROOT / "基本面/.cache"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

MAX_WORKERS = 12


# ── 工具函数 ──────────────────────────────────────────────────

def _code(value):
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits[-6:] if len(digits) >= 6 else ""


def _num(value):
    try:
        value = float(value)
        return value if pd.notna(value) else None
    except (TypeError, ValueError):
        return None


def _parse_amount(value):
    """解析 THS 金额：「17.56亿」→ 17.56e8，「6402.72万」→ 6402.72e4，「10.24万亿」→ 10.24e12"""
    if value is None:
        return None
    s = str(value).strip()
    if s.lower() in ("false", "none", "nan", ""):
        return None
    try:
        if "万亿" in s:
            return float(s.replace("万亿", "")) * 1e12
        elif "亿" in s:
            return float(s.replace("亿", "")) * 1e8
        elif "万" in s:
            return float(s.replace("万", "")) * 1e4
        else:
            return float(s)
    except (ValueError, TypeError):
        return None


def _load_stocks():
    return [
        _code(line)
        for line in Path(STOCKS_FILE).read_text("utf-8-sig").splitlines()
        if _code(line)
    ]


# ── 并行下载模块（带缓存）──────────────────────────────────────

def _fetch_one_bs(stock):
    import akshare as ak
    try:
        df = ak.stock_financial_debt_ths(symbol=stock, indicator="按报告期")
        if df is not None and not df.empty:
            df["报告期"] = pd.to_datetime(df["报告期"], errors="coerce")
            df = df.dropna(subset=["报告期"])
            return stock, df
    except Exception as e:
        pass
    return stock, None


def _fetch_one_is(stock):
    import akshare as ak
    try:
        df = ak.stock_financial_benefit_ths(symbol=stock, indicator="按报告期")
        if df is not None and not df.empty:
            df["报告期"] = pd.to_datetime(df["报告期"], errors="coerce")
            df = df.dropna(subset=["报告期"])
            return stock, df
    except Exception as e:
        pass
    return stock, None


def _load_cache(name):
    path = CACHE_DIR / f"{name}.pkl"
    if path.exists():
        return pickle.loads(path.read_bytes())
    return {}


def _save_cache(name, data):
    path = CACHE_DIR / f"{name}.pkl"
    path.write_bytes(pickle.dumps(data))


def download_parallel(stocks, fetch_fn, label, force_refresh=False):
    """多线程下载 + 本地缓存"""
    cache = {} if force_refresh else _load_cache(label)
    cached = set(cache.keys())
    remaining = [s for s in stocks if s not in cached]

    if not remaining:
        print(f"[{label}] 全部命中缓存 ({len(cache)} 只)")
        return cache

    print(f"[{label}] 缓存 {len(cached)}, 待下载 {len(remaining)} 只 (并行 {MAX_WORKERS} 线程)...")

    ok = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_fn, s): s for s in remaining}
        for i, f in enumerate(as_completed(futures), 1):
            stock, df = f.result()
            if df is not None:
                cache[stock] = df
                ok += 1
            if i % 50 == 0 or i == len(remaining):
                print(f"  [{label}] {i}/{len(remaining)} 完成, 成功 {ok}")

    _save_cache(label, cache)
    print(f"[{label}] 共 {len(cache)}/{len(stocks)} 只")
    return cache


def download_pledge_map():
    import akshare as ak
    print("[质押率] 下载...")
    df = ak.stock_gpzy_pledge_ratio_em()
    m = {}
    for _, row in df.iterrows():
        code = str(row["股票代码"]).zfill(6)
        try:
            m[code] = float(row["质押比例"]) / 100.0
        except Exception:
            continue
    print(f"[质押率] {len(m)} 只")
    return m


# ── 字段提取 ──────────────────────────────────────────────────

def extract_bs_fields(balance_sheets, stock, report_date):
    if stock not in balance_sheets:
        return {}
    df = balance_sheets[stock][
        balance_sheets[stock]["报告期"] <= pd.Timestamp(report_date)
    ]
    if df.empty:
        return {}
    row = df.sort_values("报告期").iloc[-1]

    def pick(col):
        return _parse_amount(row.get(col))

    return {
        "货币资金": pick("货币资金"),
        "负债合计": pick("负债合计"),
        "资产合计": pick("资产合计"),
        "商誉": pick("商誉"),
        "短期借款": pick("短期借款"),
        "长期借款": pick("长期借款"),
        "应付债券": pick("应付债券"),
        "所有者权益合计": pick("所有者权益（或股东权益）合计"),
    }


def extract_is_fields(benefit_sheets, stock, report_date):
    if stock not in benefit_sheets:
        return {}
    df = benefit_sheets[stock][
        benefit_sheets[stock]["报告期"] <= pd.Timestamp(report_date)
    ]
    if df.empty:
        return {}
    row = df.sort_values("报告期").iloc[-1]

    def pick(col):
        return _parse_amount(row.get(col))

    return {
        "利润总额": pick("四、利润总额"),
        "财务费用": pick("财务费用"),
        "利息费用": pick("其中：利息费用"),
        "营业利润": pick("三、营业利润"),
        "所得税费用": pick("减：所得税费用"),
        "扣非净利润": pick("扣除非经常性损益后的净利润"),
        "营业收入": pick("其中：营业收入"),
        "营业成本": pick("其中：营业成本"),
        "净利润": pick("五、净利润"),
    }


# ── 计算函数 ──────────────────────────────────────────────────

def compute_ev_ebitda(row, bs_fields, is_fields):
    """EV_EBITDA = (总市值 + 净债务) / EBITDA"""
    pe = _num(row.get("PE_TTM"))
    profit = _num(row.get("归母净利润"))
    if not pe or not profit or pe <= 0 or profit <= 0:  # 亏损企业或负PE无意义
        return None

    market_cap = pe * profit
    if market_cap <= 0:
        return None

    total_debt = bs_fields.get("负债合计")
    cash = bs_fields.get("货币资金")
    net_debt = (total_debt - cash) if (total_debt is not None and cash is not None) else 0
    ev = market_cap + net_debt

    total_profit = is_fields.get("利润总额")
    finance_expense = is_fields.get("财务费用") or 0
    if total_profit is None:
        return None

    ebitda = total_profit + abs(finance_expense)
    if ebitda <= 0:
        return None
    return round(ev / ebitda, 2)


def compute_interest_debt_ratio(bs_fields):
    """有息负债率 = (短期借款+长期借款+应付债券) / 资产合计"""
    total_assets = bs_fields.get("资产合计")
    if not total_assets or total_assets == 0:
        return None
    short = bs_fields.get("短期借款") or 0
    long_ = bs_fields.get("长期借款") or 0
    bonds = bs_fields.get("应付债券") or 0
    debt = short + long_ + bonds
    return round(debt / total_assets, 6)


def compute_interest_coverage(is_fields):
    """利息保障倍数 = (利润总额 + |利息费用|) / |利息费用|"""
    total_profit = is_fields.get("利润总额")
    expense = is_fields.get("利息费用") or is_fields.get("财务费用")
    if total_profit is None or not expense or expense == 0:
        return None
    return round((total_profit + abs(expense)) / abs(expense), 2)


def compute_goodwill_ratio(bs_fields):
    """商誉净资产比 = 商誉 / 所有者权益。若无商誉但有权益 → 0"""
    goodwill = bs_fields.get("商誉")
    equity = bs_fields.get("所有者权益合计")
    if equity is None or equity == 0:
        return None
    if goodwill is None or goodwill == 0:
        return 0.0
    return round(goodwill / equity, 6)


def compute_roic(bs_fields, is_fields):
    """ROIC = NOPAT / (权益 + 有息负债)"""
    op_profit = is_fields.get("营业利润")
    tax_expense = is_fields.get("所得税费用")
    total_profit = is_fields.get("利润总额")

    # 税率估算
    if tax_expense is not None and total_profit is not None and total_profit != 0:
        tax_rate = min(max(tax_expense / total_profit, 0), 1)
    else:
        tax_rate = 0.25  # 默认25%

    equity = bs_fields.get("所有者权益合计")
    short = bs_fields.get("短期借款") or 0
    long_ = bs_fields.get("长期借款") or 0
    bonds = bs_fields.get("应付债券") or 0

    if op_profit is None or equity is None or equity == 0:
        return None

    nopat = op_profit * (1 - tax_rate)
    invested = equity + short + long_ + bonds
    if invested <= 0:
        return None
    return round(nopat / invested, 6)


def compute_cagr_3y(benefit_sheets, stock, report_date):
    """扣非净利润3年CAGR，THS利润表历史数据。允许±90天模糊匹配"""
    if stock not in benefit_sheets:
        return None
    df = benefit_sheets[stock].copy()
    current_dt = pd.Timestamp(report_date)
    back_dt = current_dt - pd.DateOffset(years=3)

    # 当前期：降序取最近的非空
    cur_candidates = df[df["报告期"] <= current_dt].sort_values("报告期", ascending=False)
    cur_val = None
    for _, r in cur_candidates.iterrows():
        cur_val = _parse_amount(r.get("扣除非经常性损益后的净利润"))
        if cur_val is not None and cur_val != 0:
            break
    if cur_val is None or cur_val == 0:
        return None

    # 3年期候选：允许±90天
    window_start = back_dt - pd.Timedelta(days=90)
    window_end = back_dt + pd.Timedelta(days=90)
    prev_candidates = df[(df["报告期"] >= window_start) & (df["报告期"] <= window_end)].sort_values("报告期", ascending=False)
    prev_val = None
    for _, r in prev_candidates.iterrows():
        prev_val = _parse_amount(r.get("扣除非经常性损益后的净利润"))
        if prev_val is not None and prev_val != 0:
            break
    if prev_val is None or prev_val == 0:
        return None

    if cur_val * prev_val <= 0:
        return None

    cagr = (cur_val / prev_val) ** (1/3) - 1
    return round(cagr, 6)


def compute_gross_margin(is_fields):
    """毛利率 = (营业收入 - 营业成本) / 营业收入"""
    rev = is_fields.get("营业收入")
    cost = is_fields.get("营业成本")
    if rev is None or rev == 0 or cost is None:
        return None
    return round((rev - cost) / rev, 6)


def compute_net_margin(is_fields):
    """净利率 = 净利润 / 营业收入"""
    profit = is_fields.get("净利润")
    rev = is_fields.get("营业收入")
    if profit is None or rev is None or rev == 0:
        return None
    return round(profit / rev, 6)


# ── 快照富集 ──────────────────────────────────────────────────

def enrich_snapshot(snapshot_path, stocks, balance_sheets, benefit_sheets, pledge_map, label):
    print(f"\n{'='*60}")
    print(f"[{label}] {snapshot_path}")

    df = pd.read_csv(snapshot_path)
    total = len(df)

    # 确保目标列存在
    for col in ["EV_EBITDA", "有息负债率", "利息保障倍数", "商誉净资产比", "大股东质押率",
                "ROIC", "扣非净利润3年CAGR", "毛利率", "净利率"]:
        if col not in df.columns:
            df[col] = None

    before = {col: df[col].notna().sum() for col in ["EV_EBITDA", "有息负债率", "利息保障倍数",
                                                       "商誉净资产比", "大股东质押率", "ROIC",
                                                       "扣非净利润3年CAGR", "毛利率", "净利率"]}
    filled = dict.fromkeys(before, 0)
    skipped_stock = skipped_date = 0

    for idx, row in df.iterrows():
        stock = str(row.get("股票代码", "")).split(".")[0].zfill(6) if str(row.get("股票代码", "")).startswith("s") or "." in str(row.get("股票代码", "")) else str(row.get("股票代码", "")).zfill(6) if str(row.get("股票代码", "")).isdigit() else ""
        if not stock or len(stock) != 6:
            skipped_stock += 1
            continue

        report_date = str(row.get("报告期", ""))
        try:
            pd.Timestamp(report_date)
        except Exception:
            skipped_date += 1
            continue

        bs = extract_bs_fields(balance_sheets, stock, report_date)
        is_data = extract_is_fields(benefit_sheets, stock, report_date)

        # EV_EBITDA
        if pd.isna(df.at[idx, "EV_EBITDA"]):
            v = compute_ev_ebitda(row, bs, is_data)
            if v is not None:
                df.at[idx, "EV_EBITDA"] = v
                filled["EV_EBITDA"] += 1

        # 有息负债率
        if pd.isna(df.at[idx, "有息负债率"]):
            v = compute_interest_debt_ratio(bs)
            if v is not None:
                df.at[idx, "有息负债率"] = v
                filled["有息负债率"] += 1

        # 利息保障倍数
        if pd.isna(df.at[idx, "利息保障倍数"]):
            v = compute_interest_coverage(is_data)
            if v is not None:
                df.at[idx, "利息保障倍数"] = v
                filled["利息保障倍数"] += 1

        # 商誉净资产比
        if pd.isna(df.at[idx, "商誉净资产比"]):
            v = compute_goodwill_ratio(bs)
            if v is not None:
                df.at[idx, "商誉净资产比"] = v
                filled["商誉净资产比"] += 1

        # 大股东质押率
        if pd.isna(df.at[idx, "大股东质押率"]):
            if stock in pledge_map:
                df.at[idx, "大股东质押率"] = pledge_map[stock]
                filled["大股东质押率"] += 1

        # ROIC (备用计算)
        if pd.isna(df.at[idx, "ROIC"]):
            v = compute_roic(bs, is_data)
            if v is not None:
                df.at[idx, "ROIC"] = v
                filled["ROIC"] += 1

        # 扣非净利润3年CAGR (备用计算)
        if pd.isna(df.at[idx, "扣非净利润3年CAGR"]):
            v = compute_cagr_3y(benefit_sheets, stock, report_date)
            if v is not None:
                df.at[idx, "扣非净利润3年CAGR"] = v
                filled["扣非净利润3年CAGR"] += 1

        # 毛利率 (THS备用计算)
        if "毛利率" not in df.columns or pd.isna(df.at[idx, "毛利率"]):
            v = compute_gross_margin(is_data)
            if v is not None:
                if "毛利率" not in df.columns:
                    df["毛利率"] = None
                df.at[idx, "毛利率"] = v
                filled["毛利率"] = filled.get("毛利率", 0) + 1

        # 净利率 (THS备用计算)
        if "净利率" not in df.columns or pd.isna(df.at[idx, "净利率"]):
            v = compute_net_margin(is_data)
            if v is not None:
                if "净利率" not in df.columns:
                    df["净利率"] = None
                df.at[idx, "净利率"] = v
                filled["净利率"] = filled.get("净利率", 0) + 1

    df.to_csv(snapshot_path, index=False, encoding="utf-8-sig")
    print(f"  [{label}] 已写回")

    after = {col: df[col].notna().sum() for col in before}
    stats = {
        "文件": str(snapshot_path),
        "总记录": total,
        "跳过(股票码)": skipped_stock,
        "跳过(日期)": skipped_date,
    }

    for col in before:
        pct_before = f"{(before[col]/total*100):.1f}%" if total else "-"
        pct_after = f"{(after[col]/total*100):.1f}%" if total else "-"
        stats[col] = {"之前": int(before[col]), "之后": int(after[col]), "新增": filled[col],
                       "覆盖率前": pct_before, "覆盖率后": pct_after}
        print(f"  [{col}] {before[col]} → {after[col]} (+{filled[col]}) {pct_before} → {pct_after}")

    return stats


# ── 主流程 ──────────────────────────────────────────────────

def run(force_refresh=False):
    print("=" * 60)
    print("基本面补数第二阶段 — THS 报表 + 并行下载 + 缓存")
    print("=" * 60)

    stocks = list(set(_load_stocks()))
    print(f"[准备] {len(stocks)} 只股票")

    # 并行下载（缓存优先）
    t0 = time.time()
    balance_sheets = download_parallel(stocks, _fetch_one_bs, "balance_sheets", force_refresh)
    benefit_sheets = download_parallel(stocks, _fetch_one_is, "benefit_sheets", force_refresh)
    pledge_map = download_pledge_map()
    t1 = time.time()
    print(f"[下载] 耗时 {t1-t0:.0f}s")

    # 补数
    cur = enrich_snapshot(SNAPSHOT_CURRENT, stocks, balance_sheets, benefit_sheets, pledge_map, "当前快照")
    hist = enrich_snapshot(SNAPSHOT_HISTORICAL, stocks, balance_sheets, benefit_sheets, pledge_map, "历史快照")

    # 报告
    report = {
        "运行日期": date.today().isoformat(),
        "股票数": len(stocks),
        "资产负债表覆盖": len(balance_sheets),
        "利润表覆盖": len(benefit_sheets),
        "质押率覆盖": len(pledge_map),
        "耗时(秒)": round(t1 - t0, 1),
        "当前快照": cur,
        "历史快照": hist,
    }
    path = REPORT_DIR / f"补数第二阶段报告_{date.today().isoformat()}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[报告] {path}")
    print("补数第二阶段完成。")


if __name__ == "__main__":
    import sys
    refresh = "--refresh" in sys.argv
    run(force_refresh=refresh)
