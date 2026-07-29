#!/usr/bin/env python3
"""个股基本面评分准入，只约束首次开仓。"""

import os

import pandas as pd


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(path, required):
    path = path if os.path.isabs(path) else os.path.join(ROOT, path)
    if not os.path.isfile(path):
        return pd.DataFrame()
    try:
        data = pd.read_csv(path, dtype=str, keep_default_na=False)
    except (OSError, UnicodeDecodeError, pd.errors.ParserError):
        return pd.DataFrame()
    if not set(required).issubset(data.columns):
        return pd.DataFrame()
    data["股票代码"] = data["股票代码"].astype(str).str.extract(r"(\d{6})", expand=False)
    data["评分日期"] = pd.to_datetime(data["评分日期"], errors="coerce").dt.normalize()
    data["总分"] = pd.to_numeric(data["总分"], errors="coerce")
    data["置信度"] = pd.to_numeric(data["置信度"], errors="coerce")
    return data.dropna(subset=["股票代码", "评分日期", "总分", "置信度"])


def _data(state, config):
    root = state.setdefault("fundamental_score_filter", {})
    if "scores" not in root:
        root["scores"] = _load(
            config.get("个股评分文件", "基本面/个股评分结果.csv"),
            ["股票代码", "评分日期", "总分", "置信度"],
        )
    return root["scores"]


def _latest(data, code, date):
    if data.empty or not date:
        return None
    current = pd.Timestamp(str(date)[:10]).normalize()
    rows = data[(data["股票代码"] == str(code)[-6:]) & (data["评分日期"] <= current)]
    return rows.sort_values("评分日期").iloc[-1].to_dict() if not rows.empty else None


def 检查(哨兵价类型, K线数据, 状态, 配置):
    if 状态.get("已有持仓"):
        return {"通过": True, "原因": "已有持仓：基本面评分不强制平仓或阻断持仓管理", "数据状态": "持仓豁免"}
    code = K线数据.get("股票代码", K线数据.get("代码", ""))
    date = K线数据.get("日期", K线数据.get("完整时间", ""))
    row = _latest(_data(状态, 配置), code, date)
    if row is None:
        return {"通过": False, "原因": f"基本面评分历史缺失: {str(code)[-6:]}@{str(date)[:10]}", "数据状态": "缺失"}
    score = float(row["总分"])
    confidence = float(row["置信度"])
    score_floor = float(配置.get("最低总分", 65))
    confidence_floor = float(配置.get("最低置信度", 0.25))
    hard_risk = str(row.get("硬风险", "")).strip()
    if hard_risk.lower() in ("", "nan", "none"):
        hard_risk = ""
    passed = not hard_risk and score >= score_floor and confidence >= confidence_floor
    if hard_risk:
        reason = f"基本面硬风险: {hard_risk}"
    elif not passed:
        reason = f"基本面评分不足: {score:.2f}/{score_floor:.2f}，置信度{confidence:.2f}/{confidence_floor:.2f}"
    else:
        reason = "基本面评分准入通过"
    return {
        "通过": passed,
        "原因": reason,
        "数据状态": "有效",
        "基本面总分": score,
        "基本面置信度": confidence,
        "基本面评分日期": str(row["评分日期"])[:10],
    }
