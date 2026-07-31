"""Shared run and experiment identity contract for CLI and web runs."""

import hashlib
import json
import uuid
from datetime import datetime


def 生成实验身份(*, code_version, config_hash, data_version, universe_version,
             stocks, start_date, end_date, fee_config, account_mode):
    payload = {
        "code_version": code_version or "",
        "config_hash": config_hash or "",
        "data_version": data_version or "",
        "universe_version": universe_version or "",
        "stocks": sorted(str(stock) for stock in (stocks or [])),
        "start_date": str(start_date or ""),
        "end_date": str(end_date or ""),
        "fee_config": fee_config or {},
        "account_mode": str(account_mode or ""),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def 生成运行编号(prefix):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"{prefix}_{timestamp}_{uuid.uuid4().hex[:8]}"
