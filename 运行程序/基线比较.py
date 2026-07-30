"""Compare saved run summaries without recomputing trading facts."""

import json
from pathlib import Path


FIELDS = ("最终权益", "总收益率", "最大回撤", "买入次数", "卖出次数")


def _payload(run_dir):
    root = Path(run_dir)
    for name in ("多股回测结果.json", "回测结果.json"):
        path = root / name
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    summary = root / "回测摘要.json"
    return json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else {}


def 比较(baseline_dir, current_dir):
    before, after = _payload(baseline_dir), _payload(current_dir)
    before = before.get("汇总", before)
    after = after.get("汇总", after)
    differences = []
    for field in FIELDS:
        left, right = before.get(field), after.get(field)
        if left != right:
            differences.append({"字段": field, "基线": left, "当前": right})
    trade_diff = []
    for name in ("交易明细.csv", "组合成交审计.csv"):
        left_path, right_path = Path(baseline_dir) / name, Path(current_dir) / name
        if not left_path.exists() or not right_path.exists():
            continue
        import pandas as pd
        left, right = pd.read_csv(left_path, dtype=str, keep_default_na=False), pd.read_csv(right_path, dtype=str, keep_default_na=False)
        keys = [c for c in ("execution_id", "时间", "类型", "股票代码") if c in left.columns and c in right.columns]
        # 兼容单股与组合输出的成交数量字段命名。
        for frame in (left, right):
            if "成交数量" not in frame and "成交股数" in frame:
                frame["成交数量"] = frame["成交股数"]
        compare_cols = [c for c in ("成交数量", "买入价", "成交价", "卖出价", "交易费用") if c in left.columns and c in right.columns]
        if keys:
            columns = keys + compare_cols
            l = left[columns].fillna("").astype(str).sort_values(keys).to_dict("records")
            r = right[columns].fillna("").astype(str).sort_values(keys).to_dict("records")
            if l != r:
                trade_diff.append({"文件": name, "基线记录数": len(l), "当前记录数": len(r), "逐笔一致": False})
            else:
                trade_diff.append({"文件": name, "基线记录数": len(l), "当前记录数": len(r), "逐笔一致": True})
    return {
        "schema_version": "1.0",
        "baseline_run_dir": str(baseline_dir),
        "current_run_dir": str(current_dir),
        "comparison_policy": "SUMMARY_AND_TRADE_DIFF",
        "trade_differences": trade_diff,
        "identical": not differences and all(item["逐笔一致"] for item in trade_diff),
        "differences": differences,
    }
