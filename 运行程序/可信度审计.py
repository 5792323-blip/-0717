"""Generate evidence-based backtest credibility checks from saved artifacts."""

import json
import os
from pathlib import Path

import pandas as pd


def _check(name, check_id, status, **details):
    return {"check_id": check_id, "name": name, "status": status, **details}


def _股票范围编号(value, stock):
    """给逐股票证据中的执行器本地编号补上股票范围。"""
    text = str(value or "").strip()
    stock = str(stock or "").strip()
    if not text or not stock or text.startswith(f"{stock}:"):
        return text
    return f"{stock}:{text}"


def _交易文件股票代码(root, path, frame):
    """优先使用证据字段；交互式多股目录则从 股票/<代码>/ 文件路径恢复。"""
    if "股票代码" in frame and frame["股票代码"].astype(str).str.strip().ne("").all():
        return frame["股票代码"].astype(str).str.strip()
    try:
        relative = path.relative_to(root)
        parts = relative.parts
        marker = parts.index("股票")
        if marker + 1 < len(parts):
            return pd.Series(parts[marker + 1], index=frame.index)
    except (ValueError, OSError):
        pass
    return frame.get("股票代码", pd.Series("", index=frame.index)).astype(str).str.strip()


def _范围化生命周期编号(frame):
    """审计内存口径统一为 股票代码:本地生命周期编号，不改原始证据文件。"""
    if frame.empty or "股票代码" not in frame:
        return frame
    scoped = frame.copy()
    for field in ("intent_id", "order_id", "execution_id"):
        if field in scoped:
            scoped[field] = [
                _股票范围编号(value, stock)
                for value, stock in zip(scoped[field], scoped["股票代码"])
            ]
    return scoped


def 审计运行目录(run_dir):
    root = Path(run_dir)
    checks = []
    manifest = root / "运行清单.json"
    checks.append(_check("运行清单完整", "run_manifest", "PASS" if manifest.exists() else "FAIL"))
    manifest_data = {}
    if manifest.exists():
        try:
            manifest_data = json.loads(manifest.read_text(encoding="utf-8")) or {}
        except (OSError, ValueError, TypeError):
            manifest_data = {}
    trade_files = list(root.rglob("交易明细.csv"))
    if not trade_files:
        checks.append(_check("交易证据文件", "trade_evidence", "WARNING", files=0))
    else:
        checks.append(_check("交易证据文件", "trade_evidence", "PASS", files=len(trade_files)))

    frames = []
    for path in trade_files:
        try:
            frame = pd.read_csv(path, dtype=str, keep_default_na=False)
            frame["股票代码"] = _交易文件股票代码(root, path, frame)
            frame = _范围化生命周期编号(frame)
            frame["_source"] = str(path)
            frames.append(frame)
        except (OSError, ValueError, pd.errors.ParserError):
            checks.append(_check("交易文件可读取", "trade_readable", "FAIL", file=str(path)))
    trades = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    approval_path = root / "审批记录.csv"
    if not approval_path.exists():
        approval_path = root / "组合成交审计.csv"
    approvals = pd.DataFrame()
    if approval_path.exists():
        try:
            approvals = pd.read_csv(approval_path, dtype=str, keep_default_na=False)
            approvals = _范围化生命周期编号(approvals)
        except (OSError, ValueError, pd.errors.ParserError):
            checks.append(_check("审批证据可读取", "approval_readable", "FAIL"))
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
        ledger_failures = []
        inventory = {}
        sort_columns = [column for column in ("股票代码", "时间", "K线索引", "execution_id") if column in trades.columns]
        ledger_trades = trades.sort_values(sort_columns, kind="mergesort") if sort_columns else trades
        for index, row in ledger_trades.iterrows():
            stock = str(row.get("股票代码", ""))
            kind = str(row.get("类型", ""))
            qty = pd.to_numeric(row.get("成交数量"), errors="coerce")
            fee = pd.to_numeric(row.get("交易费用"), errors="coerce")
            price = pd.to_numeric(row.get("买入价" if kind == "买入" else "卖出价"), errors="coerce")
            if pd.isna(qty) or qty <= 0 or pd.isna(price) or price <= 0 or pd.isna(fee) or fee < 0:
                ledger_failures.append({"行": int(index), "execution_id": row.get("execution_id"), "原因": "数量、价格或费用无效"})
                continue
            before = inventory.get(stock, 0)
            if kind == "买入":
                total = pd.to_numeric(row.get("总成本"), errors="coerce")
                if pd.notna(total) and abs(float(total) - (float(price) * float(qty) + float(fee))) > 0.02:
                    ledger_failures.append({"行": int(index), "execution_id": row.get("execution_id"), "原因": "买入总成本不守恒"})
                inventory[stock] = before + int(qty)
            elif kind == "卖出":
                if int(qty) > before:
                    ledger_failures.append({"行": int(index), "execution_id": row.get("execution_id"), "原因": "卖出数量超过持仓"})
                inventory[stock] = max(0, before - int(qty))
                net = pd.to_numeric(row.get("卖出净金额"), errors="coerce")
                if pd.notna(net) and abs(float(net) - (float(price) * float(qty) - float(fee))) > 0.02:
                    ledger_failures.append({"行": int(index), "execution_id": row.get("execution_id"), "原因": "卖出净额不守恒"})
        checks.append(_check(
            "逐笔成交账务", "trade_ledger", "FAIL" if ledger_failures else "PASS",
            failed_count=len(ledger_failures), failures=ledger_failures[:20], ending_inventory=inventory,
        ))
    if not approvals.empty:
            result_series = approvals.get("结果", pd.Series(dtype=str))
            status_series = approvals.get("成交状态", pd.Series(dtype=str))
            approved = approvals[result_series.isin(["实际成交", "部分成交"]) & status_series.isin(["已成交", "部分成交"])] if "成交状态" in approvals else approvals[result_series.isin(["实际成交", "部分成交"])]
            filled = pd.to_numeric(approved.get("成交股数", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
            traded = pd.to_numeric(trades.get("成交数量", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
            lifecycle_failures = []
            trade_by_execution = {}
            duplicate_trade_ids = set()
            if "execution_id" in trades:
                for _, trade in trades.iterrows():
                    execution_id = str(trade.get("execution_id", "")).strip()
                    if not execution_id:
                        continue
                    if execution_id in trade_by_execution:
                        duplicate_trade_ids.add(execution_id)
                    trade_by_execution[execution_id] = trade
            if not approved.empty:
                seen_approval_ids = set()
                for index, row in approved.iterrows():
                    execution_id = str(row.get("execution_id", "")).strip()
                    trade = trade_by_execution.get(execution_id)
                    mismatch = trade is None or execution_id in seen_approval_ids
                    seen_approval_ids.add(execution_id)
                    if trade is not None:
                        approval_qty = pd.to_numeric(row.get("成交股数"), errors="coerce")
                        trade_qty = pd.to_numeric(trade.get("成交数量"), errors="coerce")
                        approval_price = pd.to_numeric(row.get("成交价"), errors="coerce")
                        trade_price = pd.to_numeric(trade.get("买入价" if str(row.get("类型")) == "买入" else "卖出价"), errors="coerce")
                        approval_fee = pd.to_numeric(row.get("交易费用"), errors="coerce")
                        trade_fee = pd.to_numeric(trade.get("交易费用"), errors="coerce")
                        mismatch = mismatch or any(
                            str(row.get(field, "")).strip() != str(trade.get(field, "")).strip()
                            for field in ("股票代码", "类型", "intent_id", "order_id", "execution_id")
                        )
                        mismatch = mismatch or any(
                            pd.isna(left) or pd.isna(right) or abs(float(left) - float(right)) > 0.02
                            for left, right in ((approval_qty, trade_qty), (approval_price, trade_price), (approval_fee, trade_fee))
                        )
                    if mismatch:
                        lifecycle_failures.append(int(index))
                if set(seen_approval_ids) != set(trade_by_execution) or duplicate_trade_ids:
                    lifecycle_failures.extend([-1] * max(1, len(set(seen_approval_ids) ^ set(trade_by_execution))))
            reconciliation_failed = (
                abs(float(filled) - float(traded)) > 0.01
                or len(approved) != len(trades)
                or bool(lifecycle_failures)
            )
            checks.append(_check(
                "审批成交对账", "approval_trade_reconciliation",
                "FAIL" if reconciliation_failed else "PASS",
                approval_filled_quantity=float(filled), trade_quantity=float(traded),
                approval_rows=int(len(approved)), trade_rows=int(len(trades)),
            ))
            checks.append(_check(
                "审批生命周期逐笔关联", "approval_lifecycle_reconciliation",
                "PASS" if not lifecycle_failures else "FAIL",
                failed_rows=lifecycle_failures[:20], failed_count=len(lifecycle_failures),
            ))
            cash_ledger_failures = []
            position_ledger_failures = []
            for index, row in approvals.iterrows():
                before_cash = pd.to_numeric(row.get("审批前现金"), errors="coerce")
                after_cash = pd.to_numeric(row.get("审批后现金"), errors="coerce")
                qty = pd.to_numeric(row.get("成交股数"), errors="coerce")
                price = pd.to_numeric(row.get("成交价"), errors="coerce")
                fee = pd.to_numeric(row.get("交易费用"), errors="coerce")
                if pd.isna(before_cash) or pd.isna(after_cash):
                    cash_ledger_failures.append(int(index)); continue
                expected = 0.0
                if str(row.get("结果")) in {"实际成交", "部分成交"} and pd.notna(qty) and pd.notna(price) and pd.notna(fee):
                    gross = float(qty) * float(price)
                    expected = -(gross + float(fee)) if str(row.get("类型")) == "买入" else gross - float(fee)
                if abs(float(after_cash) - float(before_cash) - expected) > 0.02:
                    cash_ledger_failures.append(int(index))
                before_pos = pd.to_numeric(row.get("审批前持仓"), errors="coerce")
                after_pos = pd.to_numeric(row.get("审批后持仓"), errors="coerce")
                if pd.isna(before_pos) or pd.isna(after_pos) or pd.isna(qty):
                    position_ledger_failures.append(int(index)); continue
                delta = float(qty) if str(row.get("类型")) == "买入" else -float(qty)
                if str(row.get("结果")) not in {"实际成交", "部分成交"}: delta = 0.0
                if abs(float(after_pos) - float(before_pos) - delta) > 0.01:
                    position_ledger_failures.append(int(index))
            checks.append(_check("审批现金逐笔守恒", "approval_cash_ledger", "FAIL" if cash_ledger_failures else "PASS", failed_rows=cash_ledger_failures[:20], failed_count=len(cash_ledger_failures)))
            checks.append(_check("审批持仓逐笔守恒", "approval_position_ledger", "FAIL" if position_ledger_failures else "PASS", failed_rows=position_ledger_failures[:20], failed_count=len(position_ledger_failures)))
    elif not trades.empty and str(manifest_data.get("account_mode", "")).lower() not in {"单股账户", "single", "single_stock", "独立账户", "independent", "等额独立账户"}:
        checks.append(_check(
            "审批成交对账", "approval_trade_reconciliation", "FAIL",
            reason="存在成交证据但缺少审批文件", approval_rows=0, trade_rows=int(len(trades)),
        ))
        checks.append(_check(
            "审批生命周期逐笔关联", "approval_lifecycle_reconciliation", "FAIL",
            reason="存在成交证据但缺少审批文件", failed_count=int(len(trades)),
        ))
    elif not trades.empty:
        checks.append(_check("审批成交对账", "approval_trade_reconciliation", "NOT_APPLICABLE", reason="单股账户无组合审批层"))
        checks.append(_check("审批生命周期逐笔关联", "approval_lifecycle_reconciliation", "NOT_APPLICABLE", reason="单股账户无组合审批层"))
    else:
        checks.append(_check("审批成交对账", "approval_trade_reconciliation", "NOT_APPLICABLE", reason="无成交证据"))
        checks.append(_check("审批生命周期逐笔关联", "approval_lifecycle_reconciliation", "NOT_APPLICABLE", reason="无成交证据"))
    if approval_path.exists() and approvals.empty and trades.empty:
        checks.append(_check("审批成交对账", "approval_trade_reconciliation", "WARNING", approval_rows=len(approvals), trade_rows=0))
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
    curve_count = 0
    for path in result_files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            curve_count += len(payload.get("组合权益曲线", []) or payload.get("权益曲线", []) or [])
        except (OSError, ValueError, TypeError):
            pass
    if curve_count == 0:
        process_files = list(root.rglob("持仓过程.csv"))
        for path in process_files:
            try:
                frame = pd.read_csv(path, dtype=str, keep_default_na=False)
                if not {"当前现金", "权益", "持仓市值"}.issubset(frame.columns):
                    continue
                for _, point in frame.iterrows():
                    equity = pd.to_numeric(point.get("权益"), errors="coerce")
                    cash = pd.to_numeric(point.get("当前现金"), errors="coerce")
                    market = pd.to_numeric(point.get("持仓市值"), errors="coerce")
                    if pd.isna(equity) or pd.isna(cash) or pd.isna(market):
                        continue
                    curve_count += 1
                    if abs(float(equity) - float(cash) - float(market)) > 0.02:
                        cash_failures += 1
            except (OSError, ValueError, pd.errors.ParserError):
                cash_failures += 1
    checks.append(_check(
        "资金守恒", "cash_conservation",
        "NOT_RUN" if curve_count == 0 else ("PASS" if cash_failures == 0 else "FAIL"),
        checked_count=len(result_files), curve_points=curve_count, failed_count=cash_failures,
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
        "NOT_RUN" if trades.empty else ("PASS" if lookahead_failures == 0 else "FAIL"),
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
    if manifest.exists():
        try:
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(manifest_payload, dict):
                manifest_payload["credibility_status"] = payload["overall_status"]
                manifest_payload["can_be_baseline"] = payload["can_be_baseline"]
                manifest.write_text(
                    json.dumps(manifest_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except (OSError, ValueError, TypeError):
            pass
    return payload


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    args = parser.parse_args()
    print(json.dumps(审计运行目录(args.run_dir), ensure_ascii=False, indent=2))
