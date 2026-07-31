"""Small, deterministic checks used to bind a run to its input data."""

import hashlib
import json
from pathlib import Path

import pandas as pd


def 审计行情(frame):
    dates = pd.to_datetime(frame.get("日期", pd.Series(dtype=str)), errors="coerce")
    q = ["前复权_开盘", "前复权_最高", "前复权_最低", "前复权_收盘"]
    n = frame.reindex(columns=q).apply(pd.to_numeric, errors="coerce")
    bad_ohlc = int((
        (n["前复权_最高"] < n[["前复权_开盘", "前复权_收盘", "前复权_最低"]].max(axis=1)) |
        (n["前复权_最低"] > n[["前复权_开盘", "前复权_收盘", "前复权_最高"]].min(axis=1))
    ).sum()) if len(n) else 0
    missing = int(n.isna().sum().sum())
    duplicate_dates = int(dates.dt.strftime("%Y-%m-%d").duplicated().sum())
    zero_volume = 0
    if "不复权_成交量" in frame:
        volume = pd.to_numeric(frame["不复权_成交量"], errors="coerce")
        zero_volume = int((volume <= 0).sum())
    invalid_dates = int(dates.isna().sum())
    status = "PASS" if not any((bad_ohlc, missing, duplicate_dates, invalid_dates)) else "FAIL"
    return {
        "status": status, "rows": len(frame), "start": str(dates.min())[:10],
        "end": str(dates.max())[:10], "bad_ohlc": bad_ohlc,
        "missing_prices": missing, "duplicate_dates": duplicate_dates,
        "invalid_dates": invalid_dates, "zero_volume": zero_volume,
    }


def 生成数据版本(paths, benchmark_paths=()):
    entries = []
    for path in list(paths) + list(benchmark_paths):
        path = Path(path)
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        entries.append({"path": str(path.resolve()), "sha256": digest.hexdigest(), "bytes": path.stat().st_size})
    entries.sort(key=lambda item: item["path"])
    digest = hashlib.sha256(json.dumps(entries, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {"hash": digest, "files": len(entries), "inputs": entries}
