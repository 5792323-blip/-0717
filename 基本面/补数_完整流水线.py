#!/usr/bin/env python3
"""基本面历史快照补数流水线。

处理两个快照文件中的完全空字段：
1. FCF_Yield = 自由现金流 / 总市值（总市值 ≈ PE_TTM × 归母净利润）
2. 商誉净资产比 = 商誉 / 股东权益合计（从 stock_financial_abstract 提取）
3. 大股东质押率（从 stock_gpzy_pledge_ratio_em 全局快照匹配）
4. 自由现金流（尝试从每股FCFF × 总股本改善覆盖率）

输出：更新后的快照文件 + 补数报告。
"""

import json
import time
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_CURRENT = ROOT / "数据模块/基本面历史快照.csv"
SNAPSHOT_HISTORICAL = ROOT / "数据模块/基本面历史快照_2020_2026.csv"
STOCKS_FILE = ROOT / "数据模块/hs300_list.txt"
REPORT_DIR = ROOT / "基本面/运行记录"


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

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
    if rows.empty or str(period) not in rows.columns:
        return None
    return _num(rows.iloc[0][str(period)])


def _load_stocks():
    return [_code(line) for line in Path(STOCKS_FILE).read_text("utf-8-sig").splitlines() if _code(line)]


# ---------------------------------------------------------------------------
# 补数 1: 大股东质押率（全局快照）
# ---------------------------------------------------------------------------

def fetch_pledge_map():
    """返回 dict: 股票代码(6位) → 质押比例(%)"""
    import akshare as ak

    print("[质押率] 下载全市场质押比例...")
    df = ak.stock_gpzy_pledge_ratio_em()
    pledge_map = {}
    for _, row in df.iterrows():
        code = str(row["股票代码"]).zfill(6)
        try:
            ratio = float(row["质押比例"]) / 100.0  # 百分比 → 小数
            pledge_map[code] = ratio
        except Exception:
            continue
    print(f"[质押率] 共覆盖 {len(pledge_map)} 只股票")
    return pledge_map


# ---------------------------------------------------------------------------
# 补数 2 & 3: 财务摘要提取（商誉/净资产 + 自由现金流改善）
# ---------------------------------------------------------------------------

def fetch_abstract_supplement(stocks, delay=0.15):
    """对每只股票下载 financial_abstract，提取商誉、净资产、每股FCFF。

    返回 dict: stock → {period: {商誉, 净资产, 每股FCFF}}
    """
    import akshare as ak

    supplement = {}
    for i, stock in enumerate(stocks, 1):
        try:
            abstract = ak.stock_financial_abstract(stock)
            if abstract is None or abstract.empty:
                continue
            stock_data = {}
            for col in abstract.columns:
                if not (str(col).isdigit() and len(str(col)) == 8):
                    continue
                period = str(col)
                goodwill = _pick(abstract, "商誉", period)
                if goodwill is not None and goodwill > 0:
                    goodwill = goodwill  # keep as-is (absolute value)
                elif goodwill is not None and goodwill <= 0:
                    goodwill = 0.0  # no goodwill
                net_assets = _pick(abstract, "股东权益合计(净资产)", period)
                fcf_pct = _pick(abstract, "每股企业自由现金流量", period)
                if goodwill is not None or net_assets is not None or fcf_pct is not None:
                    stock_data[period] = {
                        "商誉": goodwill,
                        "净资产": net_assets,
                        "每股FCFF": fcf_pct,
                    }
            if stock_data:
                supplement[stock] = stock_data
        except Exception as e:
            if i % 50 == 0:
                print(f"  [{i}/{len(stocks)}] 已处理，补充 {len(supplement)} 只")
        if delay:
            time.sleep(delay)
        if i % 20 == 0:
            print(f"  [{i}/{len(stocks)}] 已处理，补充 {len(supplement)} 只")
    print(f"[财务摘要] 共补充 {len(supplement)}/{len(stocks)} 只股票")
    return supplement


# ---------------------------------------------------------------------------
# 补数逻辑：快照行级别
# ---------------------------------------------------------------------------

def compute_fcf_yield(row, supplement):
    """FCF_Yield = 自由现金流 / 总市值

    总市值 ≈ PE_TTM × 归母净利润（TTM）
    """
    fcf = _num(row.get("自由现金流"))
    pe = _num(row.get("PE_TTM"))
    profit = _num(row.get("归母净利润"))
    if fcf and fcf != 0 and pe and profit and pe > 0:
        market_cap = pe * profit
        if market_cap > 0:
            return fcf / market_cap
    # 备选：使用大股东质押率隐含的总市值? No.
    return None


def compute_goodwill_ratio(row, supplement):
    """商誉净资产比 = 商誉 / 股东权益合计"""
    stock = str(row.get("股票代码", ""))
    period = str(row.get("报告期", ""))
    # 报告期格式: "2025-12-31" → 需要转成 "20251231"
    period_key = period.replace("-", "") if period else ""
    if stock in supplement and period_key in supplement[stock]:
        data = supplement[stock][period_key]
        goodwill = data.get("商誉")
        net_assets = data.get("净资产")
        if goodwill is not None and net_assets and net_assets != 0:
            return goodwill / net_assets
    return None


def improve_fcf(row, supplement):
    """若自由现金流缺失，尝试从每股FCFF × 总股本恢复"""
    existing = _num(row.get("自由现金流"))
    if existing is not None:
        return existing  # 已有值，不覆盖
    stock = str(row.get("股票代码", ""))
    period = str(row.get("报告期", "")).replace("-", "")
    if stock in supplement and period in supplement[stock]:
        data = supplement[stock][period]
        fcf_pct = data.get("每股FCFF")
        if fcf_pct is not None:
            pe = _num(row.get("PE_TTM"))
            profit = _num(row.get("归母净利润"))
            if pe and profit and pe > 0:
                market_cap = pe * profit
                # 总股本 ≈ 总市值 / PE_TTM / 每股价格? No
                # 总股本 = 归母净利润 / EPS, but we don't have EPS
                # Alternative: total_shares from abstract
                # Can't reliably compute without total shares
                pass
    return existing


# ---------------------------------------------------------------------------
# 补数 4: PE_TTM 补充（从估值文件匹配）
# ---------------------------------------------------------------------------

def merge_pe_pb(snapshot_df):
    """从历史估值文件补入 PE_TTM/PB_MRQ（相邻交易日最近匹配）"""
    valuation_file = ROOT / "数据模块/历史估值_pe_pb.csv"
    if not valuation_file.exists():
        return snapshot_df
    val = pd.read_csv(valuation_file)
    val["实际披露日"] = pd.to_datetime(val["实际披露日"], errors="coerce")
    val = val.dropna(subset=["实际披露日"]).sort_values(["股票代码", "实际披露日"])

    snapshot = snapshot_df.copy()
    snapshot["实际披露日_dt"] = pd.to_datetime(snapshot.get("实际披露日"), errors="coerce")

    # 对于 PE_TTM/PB_MRQ 缺失的行，找到最近交易日估值
    pe_missing = snapshot["PE_TTM"].isna() & snapshot["实际披露日_dt"].notna()
    pb_missing = snapshot["PB_MRQ"].isna() & snapshot["实际披露日_dt"].notna()

    if not pe_missing.any() and not pb_missing.any():
        del snapshot["实际披露日_dt"]
        return snapshot

    # 分离有日期和无日期的行，只对有日期行做 merge_asof
    mask_valid = snapshot["实际披露日_dt"].notna()
    snapshot_valid = snapshot[mask_valid].copy()
    snapshot_null = snapshot[~mask_valid].copy()

    if snapshot_valid.empty:
        if not snapshot_null.empty:
            snapshot_null = snapshot_null.drop(columns=["实际披露日_dt"], errors="ignore")
            return snapshot_null
        snapshot = snapshot.drop(columns=["实际披露日_dt"], errors="ignore")
        return snapshot

    # 按 (股票代码, 实际披露日) 排序，确保 merge_asof 正常工作
    snapshot_valid = snapshot_valid.sort_values(
        ["股票代码", "实际披露日_dt"]
    ).reset_index(drop=True)

    val = val.rename(columns={"实际披露日": "估值日期", "PE_TTM": "PE_TTM_val", "PB_MRQ": "PB_MRQ_val"})
    val_sorted = val[["股票代码", "估值日期", "PE_TTM_val", "PB_MRQ_val"]].sort_values(
        ["股票代码", "估值日期"]
    ).reset_index(drop=True)

    merged = pd.merge_asof(
        snapshot_valid,
        val_sorted,
        left_on="实际披露日_dt",
        right_on="估值日期",
        by="股票代码",
        direction="backward",
    )
    # 补 PE_TTM
    pe_mask = merged["PE_TTM"].isna() & merged["PE_TTM_val"].notna()
    merged.loc[pe_mask, "PE_TTM"] = merged.loc[pe_mask, "PE_TTM_val"]
    # 补 PB_MRQ
    pb_mask = merged["PB_MRQ"].isna() & merged["PB_MRQ_val"].notna()
    merged.loc[pb_mask, "PB_MRQ"] = merged.loc[pb_mask, "PB_MRQ_val"]

    merged = merged.drop(columns=["PE_TTM_val", "PB_MRQ_val", "估值日期", "实际披露日_dt"], errors="ignore")

    # 合并回空值行
    if not snapshot_null.empty:
        snapshot_null = snapshot_null.drop(columns=["实际披露日_dt"], errors="ignore")
        merged = pd.concat([merged, snapshot_null], ignore_index=True)
    return merged


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def enrich_snapshot(snapshot_path, stocks, supplement, pledge_map, label):
    """对单个快照文件补数并写回"""
    print(f"\n{'='*60}")
    print(f"[{label}] 处理: {snapshot_path}")

    df = pd.read_csv(snapshot_path)
    original_len = len(df)
    original_pe = df["PE_TTM"].notna().sum()
    original_fcf = df["自由现金流"].notna().sum()

    stats = {
        "文件": str(snapshot_path),
        "原始记录数": original_len,
        "原始PE_TTM填充": int(original_pe),
        "原始自由现金流填充": int(original_fcf),
        "新增字段": [],
    }

    # --- 补 PE/PB（历史估值文件） ---
    before_pe = df["PE_TTM"].notna().sum()
    before_pb = df["PB_MRQ"].notna().sum()
    total_missing = (df["PE_TTM"].isna() | df["PB_MRQ"].isna()).sum()
    if total_missing > 0 and original_len > 100:
        # 仅在历史快照（大量缺失）时尝试补 PE/PB
        try:
            df = merge_pe_pb(df)
        except Exception as e:
            print(f"  [PE/PB] 合并失败（跳过）: {e}")
    after_pe = df["PE_TTM"].notna().sum()
    print(f"  [PE/PB] 已填充 {after_pe}/{original_len} (原 {before_pe})")

    # --- 补 FCF_Yield ---
    if "FCF_Yield" not in df.columns:
        df["FCF_Yield"] = None
    fcf_yield_before = df["FCF_Yield"].notna().sum()
    fcf_yields = []
    for _, row in df.iterrows():
        fy = compute_fcf_yield(row, supplement)
        fcf_yields.append(fy)
    df["FCF_Yield"] = fcf_yields
    fcf_yield_after = df["FCF_Yield"].notna().sum()
    print(f"  [FCF_Yield] 计算完成: {fcf_yield_after}/{original_len} ({fcf_yield_after/original_len*100:.1f}%)")

    # --- 补 大股东质押率 ---
    if "大股东质押率" not in df.columns:
        df["大股东质押率"] = None
    pledge_before = df["大股东质押率"].notna().sum()
    for idx, row in df.iterrows():
        code = str(row["股票代码"]).zfill(6)
        if code in pledge_map and pd.isna(row.get("大股东质押率")):
            df.at[idx, "大股东质押率"] = pledge_map[code]
    pledge_after = df["大股东质押率"].notna().sum()
    print(f"  [大股东质押率] 补入 {pledge_after - pledge_before} 行")

    # --- 补 商誉净资产比 ---
    if "商誉净资产比" not in df.columns:
        df["商誉净资产比"] = None
    gwr_before = df["商誉净资产比"].notna().sum()
    for idx, row in df.iterrows():
        if pd.isna(row.get("商誉净资产比")):
            gr = compute_goodwill_ratio(row, supplement)
            if gr is not None:
                df.at[idx, "商誉净资产比"] = gr
    gwr_after = df["商誉净资产比"].notna().sum()
    print(f"  [商誉净资产比] 补入 {gwr_after - gwr_before} 行")

    # 写回
    df.to_csv(snapshot_path, index=False, encoding="utf-8-sig")
    print(f"  [{label}] 已写回 {snapshot_path} ({len(df)} 行)")

    # 最终统计
    stats.update({
        "最终记录数": len(df),
        "最终PE_TTM填充": int(df["PE_TTM"].notna().sum()),
        "最终PB_MRQ填充": int(df.get("PB_MRQ", pd.Series()).notna().sum()),
        "最终EV_EBITDA填充": int(df.get("EV_EBITDA", pd.Series()).notna().sum()) if "EV_EBITDA" in df.columns else 0,
        "最终FCF_Yield填充": int(df.get("FCF_Yield", pd.Series()).notna().sum()) if "FCF_Yield" in df.columns else 0,
        "最终大股东质押率填充": int(df.get("大股东质押率", pd.Series()).notna().sum()) if "大股东质押率" in df.columns else 0,
        "最终商誉净资产比填充": int(df.get("商誉净资产比", pd.Series()).notna().sum()) if "商誉净资产比" in df.columns else 0,
        "最终自由现金流填充": int(df["自由现金流"].notna().sum()),
    })
    return stats


def run():
    print("=" * 60)
    print("基本面补数完整流水线")
    print("=" * 60)

    # 1. 加载股票列表
    stocks = _load_stocks()
    unique = list(set(stocks))
    print(f"[准备] 共 {len(unique)} 只股票")

    # 2. 下载质押率（一次，全局）
    pledge_map = fetch_pledge_map()

    # 3. 下载财务摘要补充数据（每只股票一次）
    supplement = fetch_abstract_supplement(unique)

    # 4. 补充当前快照
    current_stats = enrich_snapshot(SNAPSHOT_CURRENT, unique, supplement, pledge_map, "当前快照")

    # 5. 补充历史快照
    historical_stats = enrich_snapshot(SNAPSHOT_HISTORICAL, unique, supplement, pledge_map, "历史快照")

    # 6. 生成报告
    report = {
        "运行日期": date.today().isoformat(),
        "股票数": len(unique),
        "质押率覆盖": len(pledge_map),
        "财务摘要补充": len(supplement),
        "当前快照": current_stats,
        "历史快照": historical_stats,
        "说明": "补入字段: FCF_Yield, 大股东质押率, 商誉净资产比; PE_TTM/PB_MRQ从估值文件补充",
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"补数流水线报告_{date.today().isoformat()}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[报告] {report_path}")
    print("\n补数完成。")
    return report


if __name__ == "__main__":
    run()
