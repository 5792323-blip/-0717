#!/usr/bin/env python3
"""统一的消融、Walk-forward 与策略失效判定协议。

本模块只生成实验计划和读取汇总结果，不运行回测，也不修改正式配置。
"""

import argparse
import json
import math
from datetime import date


默认因子 = [
    ("卖出规则", "atr_protective_stop"),
    ("卖出规则", "fixed_stop_loss"),
    ("扩展因子", "grid_addon_risk_limits"),
    ("过滤因子", "fundamental_universe_filter"),
    ("过滤因子", "rsi_resonance_filter"),
    ("过滤因子", "rsi_regime_adaptive_filter"),
    ("扩展因子", "position_sizing"),
]


def 生成消融方案(factors=None):
    """生成基线、逐因子开启和逐因子关闭方案。"""
    factors = list(factors or 默认因子)
    plans = [{"名称": "基线", "开启": [], "关闭": []}]
    for category, module in factors:
        plans.append({
            "名称": f"开启:{category}.{module}",
            "开启": [{"类别": category, "模块": module}],
            "关闭": [],
        })
        plans.append({
            "名称": f"关闭:{category}.{module}",
            "开启": [],
            "关闭": [{"类别": category, "模块": module}],
        })
    return plans


def 生成_walk_forward区间(start="2020-01-01", end="2026-03-31", train_years=2,
                         validation_years=1, step_years=1):
    """生成不读取未来数据的年度Walk-forward区间。"""
    start_year = date.fromisoformat(start[:10]).year
    end_year = date.fromisoformat(end[:10]).year
    windows = []
    train_start = start_year
    while train_start + train_years + validation_years - 1 <= end_year:
        train_end = train_start + train_years - 1
        validation_start = train_end + 1
        validation_end = validation_start + validation_years - 1
        windows.append({
            "训练期": [f"{train_start}-01-01", f"{train_end}-12-31"],
            "验证期": [f"{validation_start}-01-01", f"{validation_end}-12-31"],
        })
        train_start += step_years
    return windows


def _数值(value, default=None):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def 提取指标(summary):
    """兼容单股/多股汇总字段，统一成比例口径。"""
    summary = summary or {}
    return {
        "收益率": _数值(summary.get("总收益率", summary.get("组合总收益率")), 0.0),
        "年化收益率": _数值(summary.get("平均年化收益率", summary.get("年化收益率")), 0.0),
        "最大回撤": abs(_数值(summary.get("平均最大回撤", summary.get("组合最大回撤")), 0.0)),
        "胜率": _数值(summary.get("加权胜率", summary.get("胜率")), 0.0),
        "盈亏比": _数值(summary.get("平均盈亏比", summary.get("盈亏比")), 0.0),
        "交易数": int(_数值(summary.get("总交易数", summary.get("交易数")), 0) or 0),
        "最大资金使用率": _数值(summary.get("最大资金使用率"), None),
        "未实现亏损": _数值(summary.get("未实现亏损"), None),
    }


def 评估失效(summary, baseline=None, thresholds=None):
    """按风险优先输出告警；告警不改变回测结果。"""
    thresholds = {
        "最大回撤上限": 0.25,
        "最低年化收益率": 0.0,
        "最低盈亏比": 1.0,
        "最低交易数": 30,
        "胜率下降上限": 0.10,
        "最大资金使用率上限": 0.98,
        **(thresholds or {}),
    }
    metrics = 提取指标(summary)
    baseline_metrics = 提取指标(baseline) if baseline else None
    alerts = []
    if metrics["最大回撤"] > thresholds["最大回撤上限"]:
        alerts.append({"级别": "高", "指标": "最大回撤", "值": metrics["最大回撤"], "阈值": thresholds["最大回撤上限"]})
    if metrics["年化收益率"] <= thresholds["最低年化收益率"]:
        alerts.append({"级别": "高", "指标": "年化收益率", "值": metrics["年化收益率"], "阈值": thresholds["最低年化收益率"]})
    if metrics["盈亏比"] < thresholds["最低盈亏比"]:
        alerts.append({"级别": "高", "指标": "盈亏比", "值": metrics["盈亏比"], "阈值": thresholds["最低盈亏比"]})
    if metrics["交易数"] < thresholds["最低交易数"]:
        alerts.append({"级别": "中", "指标": "交易数", "值": metrics["交易数"], "阈值": thresholds["最低交易数"]})
    if baseline_metrics and metrics["胜率"] < baseline_metrics["胜率"] - thresholds["胜率下降上限"]:
        alerts.append({"级别": "中", "指标": "胜率下降", "值": metrics["胜率"], "基线": baseline_metrics["胜率"]})
    exposure = metrics["最大资金使用率"]
    if exposure is not None and exposure > thresholds["最大资金使用率上限"]:
        alerts.append({"级别": "高", "指标": "最大资金使用率", "值": exposure, "阈值": thresholds["最大资金使用率上限"]})
    return {"通过": not any(item["级别"] == "高" for item in alerts), "指标": metrics, "告警": alerts}


def 评估Walk_forward(results_by_window, thresholds=None):
    """评估验证窗口，要求每个窗口独立通过高风险约束。"""
    evaluations = []
    for window, payload in results_by_window.items():
        baseline = payload.get("基线") if isinstance(payload, dict) else None
        candidate = payload.get("候选", payload) if isinstance(payload, dict) else payload
        result = 评估失效(candidate, baseline, thresholds)
        evaluations.append({"窗口": window, **result})
    return {
        "通过": bool(evaluations) and all(item["通过"] for item in evaluations),
        "窗口结果": evaluations,
    }


def _main():
    parser = argparse.ArgumentParser(description="策略验证协议：生成实验计划或评估结果JSON")
    parser.add_argument("--result-json", help="包含汇总结果或Walk-forward结果的JSON")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2026-03-31")
    parser.add_argument("--output")
    args = parser.parse_args()
    payload = {
        "消融方案": 生成消融方案(),
        "Walk_forward区间": 生成_walk_forward区间(args.start, args.end),
        "监控阈值": {
            "最大回撤上限": 0.25, "最低年化收益率": 0.0,
            "最低盈亏比": 1.0, "最低交易数": 30,
        },
    }
    if args.result_json:
        with open(args.result_json, encoding="utf-8") as source:
            result = json.load(source)
        summary = result.get("汇总", result)
        payload["评估"] = 评估失效(summary, result.get("基线"))
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as target:
            target.write(text)
    print(text)


if __name__ == "__main__":
    _main()
