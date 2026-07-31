#!/usr/bin/env python3
"""
补数第三阶段：从新浪财经和THS报表补充风险指标
- 监管处罚次数：新浪财经违规记录页
- 诉讼仲裁次数：新浪财经诉讼仲裁页
- 关联交易风险：其他应收款/总资产（THS BS代理指标）
- 对外担保风险：预计负债/净资产（THS BS代理指标）
"""
import re
import time
import pickle
import requests
import pandas as pd
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_CURRENT = ROOT / "数据模块/基本面历史快照.csv"
SNAPSHOT_HISTORICAL = ROOT / "数据模块/基本面历史快照_2020_2026.csv"
CACHE_DIR = ROOT / "基本面/.cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ─── HTTP 工具 ───────────────────────────────────────────────
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "http://money.finance.sina.com.cn/",
}

_session = None


def _get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)
    return _session


# ─── 新浪财经违规记录 ─────────────────────────────────────────
def fetch_violations(code):
    """返回 (违规次数, 处罚类型列表, 严重度分数)"""
    cache_file = CACHE_DIR / f"violations_{code}.pkl"
    if cache_file.exists():
        return pickle.loads(cache_file.read_bytes())

    url = f"http://money.finance.sina.com.cn/corp/go.php/vGP_GetOutOfLine/stockid/{code}.phtml"
    try:
        resp = _get_session().get(url, timeout=15)
        if resp.status_code != 200:
            return (0, [], 0)

        soup = BeautifulSoup(resp.text, "html.parser")
        for table in soup.find_all("table"):
            text = table.get_text()
            if any(kw in text for kw in ["处罚决定", "整改通知", "立案调查"]):
                entries = re.findall(
                    r"(处罚决定|立案调查|整改通知|人为操纵|公开谴责|通报批评|监管关注|市场禁入|行政处罚|出具警示函|警告)\s*公告日期",
                    text,
                )
                # 严重度评分
                severity_map = {
                    "处罚决定": 3,
                    "立案调查": 3,
                    "人为操纵": 3,
                    "市场禁入": 3,
                    "行政处罚": 3,
                    "公开谴责": 2,
                    "通报批评": 2,
                    "出具警示函": 1,
                    "监管关注": 1,
                    "警告": 1,
                    "整改通知": 1,
                }
                severity = sum(severity_map.get(t, 1) for t in entries)
                result = (len(entries), entries, severity)
                cache_file.write_bytes(pickle.dumps(result))
                return result
        result = (0, [], 0)
        cache_file.write_bytes(pickle.dumps(result))
        return result
    except Exception as e:
        return (0, [], 0)


# ─── 新浪财经诉讼仲裁 ─────────────────────────────────────────
def fetch_lawsuits(code):
    """返回 诉讼次数"""
    cache_file = CACHE_DIR / f"lawsuits_{code}.pkl"
    if cache_file.exists():
        return pickle.loads(cache_file.read_bytes())

    url = f"http://money.finance.sina.com.cn/corp/go.php/vGP_Lawsuit/stockid/{code}.phtml"
    try:
        resp = _get_session().get(url, timeout=15)
        if resp.status_code != 200:
            return 0

        soup = BeautifulSoup(resp.text, "html.parser")
        for div in soup.find_all("div"):
            text = div.get_text()
            if "没有相关诉讼信息" in text:
                result = 0
                cache_file.write_bytes(pickle.dumps(result))
                return result
            if "公告日期" in text and "诉讼" in text:
                # Count unique dates
                dates = re.findall(r"(\d{4}-\d{2}-\d{2})", text)
                result = len(set(dates))
                cache_file.write_bytes(pickle.dumps(result))
                return result
        result = 0
        cache_file.write_bytes(pickle.dumps(result))
        return result
    except Exception:
        return 0


# ─── THS 报表代理指标 ─────────────────────────────────────────
def _parse_amount(value):
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


def load_bs_cache():
    """加载THS资产负债表缓存"""
    cache_file = CACHE_DIR / "balance_sheets.pkl"
    if cache_file.exists():
        return pickle.loads(cache_file.read_bytes())
    return {}


def compute_related_party_risk(bs_data, stock, report_date):
    """关联交易风险代理 = 其他应收款/资产合计"""
    if stock not in bs_data:
        return None
    df = bs_data[stock].copy()
    current_dt = pd.Timestamp(report_date)
    filtered = df[df["报告期"] <= current_dt]
    if filtered.empty:
        return None
    last = filtered.sort_values("报告期").iloc[-1]
    other_receivables = (_parse_amount(last.get("其他应收款合计"))
                         or _parse_amount(last.get("其他应收款"))
                         or _parse_amount(last.get("其他资产"))
                         or 0)
    total_assets = _parse_amount(last.get("资产合计"))
    if total_assets is None or total_assets == 0:
        return None
    return round(other_receivables / total_assets, 6)


def compute_guarantee_risk(bs_data, stock, report_date):
    """对外担保风险代理 = 预计负债/净资产。无预计负债→0"""
    if stock not in bs_data:
        return None
    df = bs_data[stock].copy()
    current_dt = pd.Timestamp(report_date)
    filtered = df[df["报告期"] <= current_dt]
    if filtered.empty:
        return None
    last = filtered.sort_values("报告期").iloc[-1]
    provision = _parse_amount(last.get("预计负债")) or 0
    equity = _parse_amount(last.get("所有者权益（或股东权益）合计"))
    if equity is None or equity == 0:
        return None
    return round(provision / equity, 6)


# ─── 主流程 ──────────────────────────────────────────────────
def main():
    print("=" * 50)
    print("补数第三阶段：风险指标")
    print("=" * 50)

    # 加载数据
    df_current = pd.read_csv(SNAPSHOT_CURRENT)
    df_hist = pd.read_csv(SNAPSHOT_HISTORICAL)
    bs_data = load_bs_cache()
    print(f"THS资产负债表缓存: {len(bs_data)} 只")
    print(f"当前快照: {len(df_current)} 条")
    print(f"历史快照: {len(df_hist)} 条")

    # ── 步骤1：批量抓取违规/诉讼数据 ──
    print("\n[1/4] 新浪财经违规/诉讼数据抓取...")
    stocks = sorted(set(str(int(c)).zfill(6) for c in df_current["股票代码"].unique()))
    print(f"  共 {len(stocks)} 只股票")

    violation_map = {}
    lawsuit_map = {}

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {}
        for stock in stocks:
            futures[executor.submit(fetch_violations, stock)] = ("v", stock)
            futures[executor.submit(fetch_lawsuits, stock)] = ("l", stock)

        done = 0
        for future in as_completed(futures):
            tag, stock = futures[future]
            try:
                result = future.result()
                if tag == "v":
                    violation_map[stock] = result[0]  # count only
                else:
                    lawsuit_map[stock] = result
            except Exception:
                pass
            done += 1
            if done % 50 == 0:
                print(f"  进度: {done}/{len(futures)}")

    print(f"  违规数据: {sum(1 for v in violation_map.values() if v > 0)} 只有违规")
    print(f"  诉讼数据: {sum(1 for v in lawsuit_map.values() if v > 0)} 只有诉讼")

    # ── 步骤2：确保目标列存在 ──
    print("\n[2/4] 确保目标列...")
    new_cols = ["监管处罚次数", "诉讼仲裁次数", "关联交易风险", "对外担保风险"]
    for df_name, df in [("当前快照", df_current), ("历史快照", df_hist)]:
        for col in new_cols:
            if col not in df.columns:
                df[col] = None
            else:
                # 统一dtype为float
                df[col] = pd.to_numeric(df[col], errors='coerce')

    # ── 步骤3：计算并填充 ──
    print("\n[3/4] 计算风险指标...")

    before = {}
    for col in new_cols:
        c_before = df_current[col].notna().sum() if col in df_current.columns else 0
        h_before = df_hist[col].notna().sum() if col in df_hist.columns else 0
        before[col] = (c_before, h_before)

    filled = {col: 0 for col in new_cols}

    # 填充当前快照
    for idx, row in df_current.iterrows():
        stock = str(int(row["股票代码"])).zfill(6)
        report_date = str(row["报告期"])

        # 监管处罚次数
        if pd.isna(df_current.at[idx, "监管处罚次数"]) or df_current.at[idx, "监管处罚次数"] == -1:
            if stock in violation_map:
                df_current.at[idx, "监管处罚次数"] = violation_map[stock]
                filled["监管处罚次数"] += 1

        # 诉讼仲裁次数
        if pd.isna(df_current.at[idx, "诉讼仲裁次数"]) or df_current.at[idx, "诉讼仲裁次数"] == -1:
            if stock in lawsuit_map:
                df_current.at[idx, "诉讼仲裁次数"] = lawsuit_map[stock]
                filled["诉讼仲裁次数"] += 1

        # 关联交易风险 (其他应收款/总资产)
        if pd.isna(df_current.at[idx, "关联交易风险"]) or df_current.at[idx, "关联交易风险"] == -1:
            v = compute_related_party_risk(bs_data, stock, report_date)
            if v is not None:
                df_current.at[idx, "关联交易风险"] = v
                filled["关联交易风险"] += 1

        # 对外担保风险 (预计负债/净资产)
        if pd.isna(df_current.at[idx, "对外担保风险"]) or df_current.at[idx, "对外担保风险"] == -1:
            v = compute_guarantee_risk(bs_data, stock, report_date)
            if v is not None:
                df_current.at[idx, "对外担保风险"] = v
                filled["对外担保风险"] += 1

    # 填充历史快照
    for idx, row in df_hist.iterrows():
        stock = str(int(row["股票代码"])).zfill(6)
        report_date = str(row["报告期"])

        if pd.isna(df_hist.at[idx, "监管处罚次数"]) or df_hist.at[idx, "监管处罚次数"] == -1:
            if stock in violation_map:
                df_hist.at[idx, "监管处罚次数"] = violation_map[stock]
                filled["监管处罚次数"] += 1

        if pd.isna(df_hist.at[idx, "诉讼仲裁次数"]) or df_hist.at[idx, "诉讼仲裁次数"] == -1:
            if stock in lawsuit_map:
                df_hist.at[idx, "诉讼仲裁次数"] = lawsuit_map[stock]
                filled["诉讼仲裁次数"] += 1

        if pd.isna(df_hist.at[idx, "关联交易风险"]) or df_hist.at[idx, "关联交易风险"] == -1:
            v = compute_related_party_risk(bs_data, stock, report_date)
            if v is not None:
                df_hist.at[idx, "关联交易风险"] = v
                filled["关联交易风险"] += 1

        if pd.isna(df_hist.at[idx, "对外担保风险"]) or df_hist.at[idx, "对外担保风险"] == -1:
            v = compute_guarantee_risk(bs_data, stock, report_date)
            if v is not None:
                df_hist.at[idx, "对外担保风险"] = v
                filled["对外担保风险"] += 1

    # ── 步骤4：保存结果 ──
    print("\n[4/4] 保存结果...")
    df_current.to_csv(SNAPSHOT_CURRENT, index=False, encoding="utf-8-sig")
    df_hist.to_csv(SNAPSHOT_HISTORICAL, index=False, encoding="utf-8-sig")

    # ── 输出报告 ──
    print("\n" + "=" * 50)
    print("补数结果")
    print("=" * 50)
    print(f"{'字段':<18} {'当前(288)':>14} {'历史(6363)':>14} {'变化':>20}")
    print("-" * 68)
    for col in new_cols:
        cb, hb = before[col]
        ca = df_current[col].notna().sum()
        ha = df_hist[col].notna().sum()
        c_pct = ca / len(df_current) * 100
        h_pct = ha / len(df_hist) * 100
        c_diff = ca - cb
        h_diff = ha - hb
        print(f"{col:<18} {ca}/{len(df_current)}={c_pct:4.1f}%  {ha}/{len(df_hist)}={h_pct:4.1f}%  +{c_diff:>3}/+{h_diff:<3}")

    print()
    print(f"违规分布: 均值={sum(violation_map.values())/len(violation_map):.1f}, "
          f"最大={max(violation_map.values())}, 中位数={sorted(violation_map.values())[len(violation_map)//2]}")
    print(f"诉讼分布: 均值={sum(lawsuit_map.values())/len(lawsuit_map):.1f}, "
          f"最大={max(lawsuit_map.values())}, 中位数={sorted(lawsuit_map.values())[len(lawsuit_map)//2]}")

    # 保存结果报告
    report = {
        "阶段": "第三阶段",
        "日期": pd.Timestamp.now().isoformat(),
        "字段": [],
    }
    for col in new_cols:
        ca = df_current[col].notna().sum()
        ha = df_hist[col].notna().sum()
        report["字段"].append(
            {
                "字段名": col,
                "当前快照": f"{ca}/{len(df_current)} ({ca/len(df_current)*100:.1f}%)",
                "历史快照": f"{ha}/{len(df_hist)} ({ha/len(df_hist)*100:.1f}%)",
            }
        )

    import json

    report_file = ROOT / "基本面/运行记录/补数第三阶段报告.json"
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已保存: {report_file}")


if __name__ == "__main__":
    main()
