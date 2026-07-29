#!/usr/bin/env python3
"""根据历史基本面快照计算五维评分、置信度和准入结论。"""

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml


DIMENSIONS = {
    "盈利质量": {
        "weight": 0.30,
        "metrics": {"ROIC": (0.40, True), "ROE": (0.30, True), "FCF净利比": (0.30, True)},
    },
    "成长质量": {
        "weight": 0.25,
        "metrics": {"收入3年CAGR": (0.30, True), "扣非净利润3年CAGR": (0.35, True),
                     "收入同比": (0.15, True), "扣非净利润同比": (0.20, True)},
    },
    "财务健康": {
        "weight": 0.20,
        "metrics": {"资产负债率": (0.25, False), "有息负债率": (0.25, False),
                     "利息保障倍数": (0.20, True), "应收周转天数": (0.15, False),
                     "存货周转天数": (0.15, False)},
    },
    "估值合理性": {
        "weight": 0.15,
        "metrics": {"PE_TTM": (0.30, False), "PB_MRQ": (0.20, False),
                     "EV_EBITDA": (0.20, False), "FCF_Yield": (0.30, True)},
    },
    "治理与事件风险": {
        "weight": 0.10,
        "metrics": {"审计意见": (0.30, True), "监管处罚次数": (0.25, False),
                     "大股东质押率": (0.20, False), "商誉净资产比": (0.15, False),
                     "关联交易风险": (0.10, False)},
    },
}

SOURCE_CONFIDENCE = {"官方": 1.0, "授权": 1.0, "专业": 0.95, "公开": 0.85, "手工导入": 0.75}
AUDIT_SCORE = {"标准无保留意见": 10, "无保留意见": 10, "保留意见": 4,
               "无法表示意见": 1, "否定意见": 1}


def _number(series):
    return pd.to_numeric(series, errors="coerce")


def _percentile(values, value, higher_is_better):
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if pd.isna(value) or len(clean) == 0:
        return None
    # 单一可用观测只能给中性分，避免把样本不足误判成高分。
    if len(clean) == 1:
        return 5.5
    rank = (clean <= value).mean()
    if not higher_is_better:
        rank = 1.0 - rank
    return max(1.0, min(10.0, 1.0 + 9.0 * rank))


def _metric_value(row, metric):
    if metric == "审计意见":
        return AUDIT_SCORE.get(str(row.get(metric, "")).strip())
    value = row.get(metric)
    try:
        value = float(value)
        return value if pd.notna(value) else None
    except (TypeError, ValueError):
        return None


def _freshness(row, config):
    try:
        score_date = pd.Timestamp(row["评分日期"])
        disclosure = pd.Timestamp(row["实际披露日"])
        age = max(0, (score_date - disclosure).days)
    except (KeyError, TypeError, ValueError):
        return 0.0
    limit = int(config.get("时效天数", {}).get("季度财务", 180))
    return max(0.25, 1.0 - age / max(limit, 1))


def _source_factor(row):
    source = str(row.get("来源等级", row.get("数据来源", "手工导入")))
    for key, factor in SOURCE_CONFIDENCE.items():
        if key in source:
            return factor
    return 0.70


def _hard_risks(row, config):
    risks = []
    audit = str(row.get("审计意见", "")).strip()
    if config.get("硬风险", {}).get("否定意见或无法表示意见", True) and audit in ("否定意见", "无法表示意见"):
        risks.append(audit)
    if config.get("硬风险", {}).get("重大资金占用", True) and str(row.get("关联交易风险", "")).strip() in ("重大资金占用", "是"):
        risks.append("重大资金占用")
    if config.get("硬风险", {}).get("立案未结", True) and str(row.get("重大诉讼标记", "")).strip() in ("立案未结", "是"):
        risks.append("立案未结")
    return risks


def 计算评分(frame, config=None):
    config = config or {}
    frame = frame.copy()
    output = []
    for _, row in frame.iterrows():
        result = {"股票代码": row.get("股票代码"), "评分日期": row.get("评分日期")}
        dimension_scores = {}
        total_weight = 0.0
        weighted_total = 0.0
        coverage_total = 0.0
        for dimension, spec in DIMENSIONS.items():
            valid = []
            for metric, (metric_weight, higher) in spec["metrics"].items():
                value = _metric_value(row, metric)
                if value is not None:
                    valid.append((metric, metric_weight, higher, value))
            if not valid:
                dimension_scores[dimension] = None
                result[f"{dimension}覆盖率"] = 0.0
                continue
            scored = []
            for metric, metric_weight, higher, value in valid:
                peers = frame
                if "行业名称" in frame.columns and pd.notna(row.get("行业名称")):
                    industry_peers = frame[frame["行业名称"] == row.get("行业名称")]
                    if len(industry_peers) >= int(config.get("准入阈值", {}).get("行业横截面最小样本数", 20)):
                        peers = industry_peers
                peers = peers[peers["评分日期"] == row.get("评分日期")] if "评分日期" in peers.columns else peers
                peer_values = peers[metric].map(lambda x: AUDIT_SCORE.get(str(x).strip()) if metric == "审计意见" else x) if metric in peers else pd.Series(dtype=float)
                score = _percentile(peer_values, value, higher)
                if score is not None:
                    scored.append((metric_weight, score))
            metric_weight_total = sum(weight for weight, _ in spec["metrics"].values())
            coverage = sum(weight for weight, _ in scored) / metric_weight_total
            dimension_score = sum(weight * score for weight, score in scored) / max(sum(weight for weight, _ in scored), 1e-9)
            dimension_scores[dimension] = dimension_score
            result[f"{dimension}覆盖率"] = round(coverage, 4)
            if coverage > 0:
                weighted_total += spec["weight"] * dimension_score
                total_weight += spec["weight"]
                coverage_total += spec["weight"] * coverage
        total_score = weighted_total / max(total_weight, 1e-9) * 10
        coverage_factor = coverage_total / max(sum(item["weight"] for item in DIMENSIONS.values()), 1e-9)
        confidence = coverage_factor * _freshness(row, config) * _source_factor(row)
        risks = _hard_risks(row, config)
        allow_score = float(config.get("准入阈值", {}).get("基本面允许分数", 75))
        observation_score = float(config.get("准入阈值", {}).get("观察分数", 65))
        formal_confidence = float(config.get("准入阈值", {}).get("正式准入置信度", 0.80))
        minimum_confidence = float(config.get("准入阈值", {}).get("最低置信度", 0.60))
        if risks:
            decision = "禁止新开仓"
        elif total_score >= allow_score and confidence >= formal_confidence:
            decision = "基本面允许"
        elif total_score >= observation_score and confidence >= minimum_confidence:
            decision = "观察"
        elif confidence < minimum_confidence:
            decision = "数据不足"
        else:
            decision = "基本面不准入"
        result.update({"盈利质量评分": round(dimension_scores.get("盈利质量") or 0, 4),
                       "成长质量评分": round(dimension_scores.get("成长质量") or 0, 4),
                       "财务健康评分": round(dimension_scores.get("财务健康") or 0, 4),
                       "估值合理性评分": round(dimension_scores.get("估值合理性") or 0, 4),
                       "治理与事件风险评分": round(dimension_scores.get("治理与事件风险") or 0, 4),
                       "总分": round(total_score, 4), "置信度": round(confidence, 4),
                       "评分状态": "数据不足" if confidence < minimum_confidence else "可评价",
                       "硬风险": "、".join(risks), "准入结论": decision})
        output.append(result)
    return pd.DataFrame(output)


def main():
    parser = argparse.ArgumentParser(description="计算个股五维基本面评分")
    parser.add_argument("input", nargs="?", default="数据模块/基本面历史快照.csv")
    parser.add_argument("--output", default="基本面/个股评分结果.csv")
    parser.add_argument("--config", default="基本面/个股评分配置.yaml")
    args = parser.parse_args()
    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"未找到输入文件：{input_path}；请先导入真实基本面快照。")
    with open(args.config, encoding="utf-8") as source:
        config = yaml.safe_load(source) or {}
    result = 计算评分(pd.read_csv(input_path, dtype=str), config)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(json.dumps({"输出": args.output, "行数": len(result), "结论统计": result["准入结论"].value_counts().to_dict()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
