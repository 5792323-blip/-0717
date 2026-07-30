"""Safe lifecycle operations for completed backtest result directories."""

import json
import os
import shutil
from pathlib import Path


CORE_FILES = {
    "运行清单.json", "可信度审计.json", "多股回测结果.json",
    "交互回测报告.html", "多股策略决策回放.html",
    "组合成交审计.csv", "交易明细.csv", "持仓过程.csv", "回测摘要.txt",
}


def _manifest(root):
    path = root / "运行清单.json"
    try:
        return path, json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return path, {}


def 锁定(run_dir):
    root = Path(run_dir).resolve()
    path, data = _manifest(root)
    if not data:
        raise ValueError("结果目录缺少运行清单")
    data["locked"] = True
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def 目录状态(run_dir):
    root = Path(run_dir).resolve()
    _, data = _manifest(root)
    files = []
    total = 0
    for path in root.rglob("*"):
        if path.is_file():
            size = path.stat().st_size
            total += size
            files.append({"路径": str(path.relative_to(root)), "字节数": size})
    return {"run_id": data.get("run_id", root.name), "locked": bool(data.get("locked")), "字节数": total, "文件数": len(files), "文件": files}


def 清理可重建深度数据(run_dir, confirm=False):
    root = Path(run_dir).resolve()
    _, data = _manifest(root)
    if data.get("locked"):
        raise PermissionError("结果已锁定，不能清理")
    if not confirm:
        raise ValueError("清理操作需要 confirm=True")
    removed = []
    for path in root.rglob("*"):
        if not path.is_file() or path.name in CORE_FILES:
            continue
        if path.name in {"回放行情.csv.gz", "策略决策回放.html"} or path.parts[-2:] == ("checkpoint", "latest.json"):
            removed.append(str(path.relative_to(root)))
            path.unlink()
    return {"删除文件": removed, "删除数量": len(removed)}


def 解锁(run_dir):
    root = Path(run_dir).resolve()
    path, data = _manifest(root)
    if not data:
        raise ValueError("结果目录缺少运行清单")
    data["locked"] = False
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
