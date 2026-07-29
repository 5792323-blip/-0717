#!/usr/bin/env python3
"""行业景气历史准入过滤。

只使用交易日当时已经生效的行业归属与行业景气评分。任一历史记录缺失时
默认拦截新开仓，避免使用当前行业分类或事后评分污染回测。
"""

import os

import pandas as pd


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _代码(value):
    return str(value).zfill(6)[-6:]


def _读取(path, required):
    if not path:
        return pd.DataFrame()
    path = path if os.path.isabs(path) else os.path.join(项目根目录, path)
    if not os.path.isfile(path):
        return pd.DataFrame()
    try:
        data = pd.read_csv(path)
    except (OSError, UnicodeDecodeError, pd.errors.ParserError):
        return pd.DataFrame()
    if not set(required).issubset(data.columns):
        return pd.DataFrame()
    data = data.copy()
    data["生效日期"] = pd.to_datetime(data["生效日期"], errors="coerce").dt.normalize()
    if "股票代码" in data:
        data["股票代码"] = data["股票代码"].map(_代码)
    if "行业景气指数" in data:
        data["行业景气指数"] = pd.to_numeric(data["行业景气指数"], errors="coerce")
    return data.dropna(subset=required).sort_values("生效日期")


def _数据(状态, 配置):
    root = 状态.setdefault("industry_boom_filter", {})
    if "行业归属" not in root:
        root["行业归属"] = _读取(
            配置.get("历史行业归属文件", ""), ["股票代码", "生效日期", "行业名称"]
        )
        root["行业评分"] = _读取(
            配置.get("历史行业评分文件", ""), ["行业名称", "生效日期", "行业景气指数"]
        )
    return root["行业归属"], root["行业评分"]


def _最新(data, condition, date):
    if data.empty or not date:
        return None
    current = pd.Timestamp(str(date)[:10]).normalize()
    rows = data[condition(data) & (data["生效日期"] <= current)]
    return rows.iloc[-1].to_dict() if not rows.empty else None


def 检查(哨兵价类型, K线数据, 状态, 配置):
    # 行业轮动只约束新开仓；被选出后不因行业评分变化被动平仓。
    if 状态.get("已有持仓"):
        return {"通过": True, "原因": "已有持仓：行业景气过滤不强制平仓或阻断持仓管理", "数据状态": "持仓豁免"}

    code = _代码(K线数据.get("股票代码", K线数据.get("代码", "")))
    date = K线数据.get("日期", K线数据.get("完整时间", ""))
    industries, scores = _数据(状态, 配置)
    industry = _最新(industries, lambda data: data["股票代码"] == code, date)
    if industry is None:
        return {"通过": False, "原因": f"历史行业归属缺失: {code or '未知股票'}@{str(date)[:10]}", "数据状态": "缺失"}
    score = _最新(scores, lambda data: data["行业名称"] == industry["行业名称"], date)
    if score is None:
        return {"通过": False, "原因": f"历史行业评分缺失: {industry['行业名称']}@{str(date)[:10]}", "数据状态": "缺失"}

    threshold = float(配置.get("行业景气指数下限", 6.0))
    value = float(score["行业景气指数"])
    passed = value >= threshold
    return {
        "通过": passed,
        "原因": "行业景气准入通过" if passed else f"行业景气指数不足: {value:.2f} < {threshold:.2f}",
        "数据状态": "有效",
        "行业名称": industry["行业名称"],
        "行业归属生效日期": str(industry["生效日期"])[:10],
        "行业评分生效日期": str(score["生效日期"])[:10],
        "行业景气指数": value,
    }
