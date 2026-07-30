"""Generate evidence-based backtest credibility checks from saved artifacts."""

import json
import os
from pathlib import Path

import pandas as pd


def _check(name, check_id, status, **details):
    return {"check_id": check_id, "name": name, "status": status, **details}


def 审计运行目录(run_dir):
    root = Path(run_dir)
    checks = []
    manifest = root / "运行清单.json"
    checks.append(_check("运行清单完整", "run_manifest", "PASS" if manifest.exists() else "FAIL"))
    trade_files = list(root.rglob("交易明细.csv"))
    if not trade_files:
        checks.append(_check("交易证据文件", "trade_evidence", "WARNING", files=0))
    else:
        checks.append(_check("交易证据文件", "trade_evidence", "PASS", files=len(trade_files)))

    frames = []
    for path in trade_files:
        try:
            frame = pd.read_csv(path, dtype=str, keep_default_na=False)
            frame["_source"] = str(path)
            frames.append(frame)
        except (OSError, ValueError, pd.errors.ParserError):
            checks.append(_check("交易文件可读取", "trade_readable", "FAIL", file=str(path)))
    trades = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not trades.empty:
        ids = ["intent_id", "order_id", "execution_id"]
        missing = [c for c in ids if c not in trades.columns]
        checks.append(_check(
            "交易生命周期编号", "event_ids",
            "PASS" if not missing and trades[ids].replace("", pd.NA).notna().all().all() else "WARNING",
            missing_fields=missing,
        ))
        if "execution_id" in trades:
            duplicates = int(trades["execution_id"].replace("", pd.NA).duplicated(keep=False).sum())
            checks.append(_check(
                "重复成交检查", "duplicate_execution", "FAIL" if duplicates else "PASS",
                failed_count=duplicates,
            ))
        price_cols = [c for c in ("前复权成交价", "买入价", "卖出价") if c in trades]
        invalid = 0
        for col in price_cols:
            values = pd.to_numeric(trades[col], errors="coerce")
            invalid += int((values.dropna() <= 0).sum())
        checks.append(_check(
            "成交价格有效", "valid_execution_price", "FAIL" if invalid else "PASS",
            failed_count=invalid,
        ))
        if "交易费用" in trades:
            fee = pd.to_numeric(trades["交易费用"], errors="coerce")
            checks.append(_check(
                "费用记录覆盖", "fee_coverage",
                "PASS" if fee.notna().all() else "WARNING",
                recorded_trades=int(fee.notna().sum()),
                missing_trades=int(fee.isna().sum()),
            ))
        else:
            checks.append(_check("费用记录覆盖", "fee_coverage", "WARNING", missing_trades=len(trades)))
    cash_failures = 0
    result_files = list(root.glob("多股回测结果.json")) + list(root.glob("回测结果.json"))
    # 单股结果有时只保存权益曲线，统一纳入守恒检查。
    if not result_files:
        result_files = list(root.rglob("回测结果.json"))
    for path in result_files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            curves = payload.get("组合权益曲线", []) or payload.get("权益曲线", [])
            for point in curves:
                equity = float(point.get("权益", point.get("当前权益", 0)) or 0)
                cash = float(point.get("现金", 0) or 0)
                market = float(point.get("持仓市值", 0) or 0)
                if abs(equity - cash - market) > 0.02:
                    cash_failures += 1
        except (OSError, ValueError, TypeError):
            cash_failures += 1
    checks.append(_check(
        "资金守恒", "cash_conservation",
        "PASS" if result_files and cash_failures == 0 else "WARNING",
        checked_count=len(result_files), failed_count=cash_failures,
    ))
    lookahead_failures = 0
    for _, row in trades.iterrows() if not trades.empty else []:
        price = pd.to_numeric(row.get("前复权成交价"), errors="coerce")
        low = pd.to_numeric(row.get("信号K线_最低"), errors="coerce")
        high = pd.to_numeric(row.get("信号K线_最高"), errors="coerce")
        if pd.notna(price) and pd.notna(low) and pd.notna(high) and (price < low - 1e-6 or price > high + 1e-6):
            lookahead_failures += 1
    checks.append(_check(
        "未来数据检查", "lookahead",
        "PASS" if lookahead_failures == 0 else "FAIL",
        checked_count=len(trades), failed_count=lookahead_failures,
    ))
    statuses = {item["status"] for item in checks}
    overall = "FAIL" if "FAIL" in statuses else "WARNING" if {"WARNING", "NOT_RUN"} & statuses else "PASS"
    payload = {
        "schema_version": "1.0",
        "overall_status": overall,
        "can_be_baseline": overall == "PASS",
        "checks": checks,
    }
    path = root / "可信度审计.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    args = parser.parse_args()
    print(json.dumps(审计运行目录(args.run_dir), ensure_ascii=False, indent=2))
