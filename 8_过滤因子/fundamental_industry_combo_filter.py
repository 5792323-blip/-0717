#!/usr/bin/env python3
"""个股基本面与行业景气联合准入过滤。

只约束新开仓；已有持仓不因评分变化被动平仓。输入必须是按历史评分日
生成的个股评分结果和按生效日生成的行业景气历史评分。
"""

import os

import pandas as pd


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
    return data


def _数据(状态, 配置):
    root = 状态.setdefault("fundamental_industry_combo_filter", {})
    if "个股评分" not in root:
        root["个股评分"] = _读取(
            配置.get("个股评分文件", "基本面/个股评分结果.csv"),
            ["股票代码", "评分日期", "总分", "置信度", "准入结论"],
        )
        root["行业评分"] = _读取(
            配置.get("行业评分文件", "基本面/历史数据/行业景气评分历史.csv"),
            ["行业名称", "生效日期", "行业景气指数", "覆盖权重"],
        )
        root["行业归属"] = _读取(
            配置.get("行业归属文件", "基本面/历史数据/股票行业归属历史.csv"),
            ["股票代码", "生效日期", "行业名称"],
        )
        for name in ("个股评分", "行业评分", "行业归属"):
            data = root[name]
            if "股票代码" in data:
                data["股票代码"] = data["股票代码"].astype(str).str.extract(r"(\d{6})", expand=False)
            for column in ("评分日期", "生效日期"):
                if column in data:
                    data[column] = pd.to_datetime(data[column], errors="coerce").dt.normalize()
    return root["个股评分"], root["行业评分"], root["行业归属"]


def _最新(data, condition, date):
    if data.empty or not date:
        return None
    current = pd.Timestamp(str(date)[:10]).normalize()
    rows = data[condition(data) & (data["评分日期"] <= current if "评分日期" in data else data["生效日期"] <= current)]
    return rows.sort_values("评分日期" if "评分日期" in rows else "生效日期").iloc[-1].to_dict() if not rows.empty else None


def 检查(哨兵价类型, K线数据, 状态, 配置):
    if 状态.get("已有持仓"):
        return {"通过": True, "原因": "已有持仓：联合评分不强制平仓或阻断持仓管理", "数据状态": "持仓豁免"}
    scores, industry_scores, assignments = _数据(状态, 配置)
    code = str(K线数据.get("股票代码", K线数据.get("代码", "")))[-6:]
    date = K线数据.get("日期", K线数据.get("完整时间", ""))
    stock = _最新(scores, lambda data: data["股票代码"] == code, date)
    if stock is None:
        return {"通过": False, "原因": f"个股基本面评分缺失: {code}@{str(date)[:10]}", "数据状态": "缺失"}
    assignment = _最新(assignments, lambda data: data["股票代码"] == code, date)
    if assignment is None:
        return {"通过": False, "原因": f"历史行业归属缺失: {code}@{str(date)[:10]}", "数据状态": "缺失"}
    industry = _最新(industry_scores, lambda data: data["行业名称"] == assignment["行业名称"], date)
    if industry is None:
        return {"通过": False, "原因": f"历史行业评分缺失: {assignment['行业名称']}@{str(date)[:10]}", "数据状态": "缺失"}

    stock_score = float(stock.get("总分", 0) or 0)
    industry_score = float(industry.get("行业景气指数", 0) or 0) * 10.0
    stock_confidence = float(stock.get("置信度", 0) or 0)
    industry_coverage = float(industry.get("覆盖权重", 0) or 0)
    combined = stock_score * float(配置.get("个股权重", 0.60)) + industry_score * float(配置.get("行业权重", 0.40))
    confidence = stock_confidence * industry_coverage
    hard_risk = str(stock.get("硬风险", "")).strip()
    if hard_risk.lower() in ("", "nan", "none"):
        hard_risk = ""
    threshold = float(配置.get("综合准入分数", 75))
    min_confidence = float(配置.get("最低置信度", 0.80))
    passed = not hard_risk and combined >= threshold and confidence >= min_confidence
    reason = "联合评分准入通过" if passed else (
        f"联合评分不足: 个股{stock_score:.2f}，行业{industry_score:.2f}，综合{combined:.2f}，置信度{confidence:.2f}"
        if not hard_risk else f"个股硬风险: {hard_risk}"
    )
    return {
        "通过": passed, "原因": reason, "数据状态": "有效",
        "股票代码": code, "行业名称": assignment["行业名称"],
        "个股基本面分": stock_score, "行业景气分": industry_score,
        "综合评分": round(combined, 4), "联合置信度": round(confidence, 4),
        "个股评分日期": str(stock.get("评分日期", ""))[:10],
        "行业评分生效日期": str(industry.get("生效日期", ""))[:10],
    }
