#!/usr/bin/env python3
"""基本面股票池准入过滤。

数据必须包含生效日期，检查时只使用 ``生效日期 <= 当前交易日`` 的最新快照。
缺少历史时点数据时默认拦截，避免把当前基本面倒灌到历史回测。
"""

import json
import os

import pandas as pd


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


字段别名 = {
    "股票代码": ["股票代码", "代码", "stock_code"],
    "生效日期": ["生效日期", "披露日期", "available_date", "date"],
    "PE": ["PE", "市盈率", "pe"],
    "行业PE": ["行业PE", "行业市盈率", "industry_pe"],
    "ROE": ["ROE", "净资产收益率", "roe"],
    "近3年净利CAGR": ["近3年净利CAGR", "净利润3年复合增长率", "net_profit_cagr_3y"],
    "资产负债率": ["资产负债率", "debt_ratio"],
    "经营现金流净利润比": ["经营现金流净利润比", "cfo_to_net_profit"],
    "行业景气指数": ["行业景气指数", "industry_boom_score"],
}


def _找列(data, names):
    for name in names:
        if name in data.columns:
            return name
    return None


def _标准化(data):
    if data is None or data.empty:
        return pd.DataFrame()
    rename = {}
    for target, names in 字段别名.items():
        source = _找列(data, names)
        if source:
            rename[source] = target
    data = data.rename(columns=rename).copy()
    required = set(字段别名)
    if not required.issubset(data.columns):
        return pd.DataFrame()
    data["股票代码"] = data["股票代码"].astype(str).str.extract(r"(\d{6})", expand=False)
    data["生效日期"] = pd.to_datetime(data["生效日期"], errors="coerce").dt.normalize()
    return data.dropna(subset=["股票代码", "生效日期"]).sort_values("生效日期")


def _读取文件(path):
    if not path:
        return pd.DataFrame()
    path = path if os.path.isabs(path) else os.path.join(项目根目录, path)
    if not os.path.isfile(path):
        return pd.DataFrame()
    try:
        suffix = os.path.splitext(path)[1].lower()
        if suffix == ".csv":
            return _标准化(pd.read_csv(path))
        if suffix in (".pkl", ".pickle"):
            return _标准化(pd.read_pickle(path))
        if suffix == ".json":
            with open(path, encoding="utf-8") as source:
                return _标准化(pd.DataFrame(json.load(source)))
    except (OSError, ValueError, TypeError, KeyError):
        return pd.DataFrame()
    return pd.DataFrame()


def _数据(状态, 配置):
    root = 状态.setdefault("fundamental_universe_filter", {})
    if "数据" not in root:
        root["数据"] = _读取文件(配置.get("历史数据文件", ""))
    return root["数据"]


def _取快照(data, code, date):
    if data.empty or not code or not date:
        return None
    current = pd.Timestamp(str(date)[:10]).normalize()
    rows = data[(data["股票代码"] == str(code)[-6:]) & (data["生效日期"] <= current)]
    return rows.iloc[-1].to_dict() if not rows.empty else None


def 检查(哨兵价类型, K线数据, 状态, 配置):
    # 股票池只约束新开仓；已有持仓的卖出和网格生命周期由其他模块管理。
    if 状态.get("已有持仓"):
        return {"通过": True, "原因": "已有持仓：基本面过滤不强制平仓或阻断持仓管理", "数据状态": "持仓豁免"}
    data = _数据(状态, 配置)
    code = K线数据.get("股票代码", K线数据.get("代码", ""))
    date = K线数据.get("日期", K线数据.get("完整时间", ""))
    snapshot = _取快照(data, code, date)
    if snapshot is None:
        return {
            "通过": False,
            "原因": f"基本面历史快照缺失: {str(code)[-6:] or '未知股票'}@{str(date)[:10]}",
            "数据状态": "缺失",
        }

    thresholds = {
        "PE相对行业折价": float(snapshot["PE"]) <= float(snapshot["行业PE"]) * float(配置.get("PE相对行业倍数", 0.8)),
        "ROE": float(snapshot["ROE"]) >= float(配置.get("ROE下限", 0.15)),
        "近3年净利增长": float(snapshot["近3年净利CAGR"]) >= float(配置.get("近3年净利CAGR下限", 0.20)),
        "财务健康": (
            float(snapshot["资产负债率"]) <= float(配置.get("资产负债率上限", 0.50))
            and float(snapshot["经营现金流净利润比"]) >= float(配置.get("经营现金流净利润比下限", 0.80))
        ),
        "行业景气": float(snapshot["行业景气指数"]) >= float(配置.get("行业景气指数下限", 0.0)),
    }
    passed = all(thresholds.values())
    failed = [name for name, ok in thresholds.items() if not ok]
    return {
        "通过": passed,
        "原因": "基本面准入通过" if passed else "基本面因子未达标: " + "、".join(failed),
        "数据状态": "有效",
        "生效日期": str(snapshot["生效日期"])[:10],
        "因子明细": thresholds,
    }
