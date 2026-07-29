#!/usr/bin/env python3
"""一键审计并生成个股+行业联合评分所需文件。"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import yaml

# Allow direct execution from the repository root or from 基本面/.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from 基本面.计算个股评分 import 计算评分
from 基本面.导入个股基本面快照 import 审计 as 审计个股快照
from 基本面.审计行业景气当前台账 import 审计 as 审计行业台账
from 基本面.生成个股研究排序 import 生成 as 生成研究排序, 审计 as 审计研究覆盖率
from 基本面.生成基本面研究池 import 生成 as 生成研究池, 报告 as 研究池报告
from 基本面.审计个股历史基本面 import 审计 as 审计个股历史基本面


SNAPSHOT = ROOT / "数据模块/基本面历史快照.csv"
SCORE_OUTPUT = ROOT / "基本面/个股评分结果.csv"
RESEARCH_OUTPUT = ROOT / "基本面/个股研究排序.csv"
RESEARCH_AUDIT = ROOT / "基本面/运行记录/个股覆盖率审计.json"
POOL_OUTPUT = ROOT / "基本面/基本面研究池.csv"
POOL_REPORT = ROOT / "基本面/运行记录/基本面研究池报告.json"
HISTORICAL_AUDIT = ROOT / "基本面/运行记录/个股历史基本面审计.json"
INDUSTRY_HISTORY = ROOT / "基本面/历史数据/行业景气评分历史.csv"
INDUSTRY_INPUT = ROOT / "基本面/历史数据/行业指标评分历史.csv"
WORKBOOK = ROOT / "基本面/全行业景气度量化跟踪体系_v3_全行业核心驱动版.xlsx"
REPORT = ROOT / "基本面/运行记录/联合评分管线报告.json"


def _industry_history_ready():
    if not INDUSTRY_HISTORY.exists():
        return False, {"原因": "行业景气评分历史文件不存在"}
    data = pd.read_csv(INDUSTRY_HISTORY)
    required = {"行业名称", "生效日期", "行业景气指数", "数据截止日", "覆盖权重"}
    if data.empty:
        return False, {"原因": "行业景气评分历史为空"}
    if not required.issubset(data.columns):
        return False, {"原因": "行业景气评分历史字段不完整"}
    start = pd.to_datetime(data["生效日期"], errors="coerce")
    cutoff = pd.to_datetime(data["数据截止日"], errors="coerce")
    if (cutoff > start).any():
        return False, {"原因": "行业评分存在前视日期"}
    if (pd.to_numeric(data["覆盖权重"], errors="coerce") < 0.9).any():
        return False, {"原因": "行业评分存在覆盖率低于90%的记录"}
    return True, {"记录数": len(data), "行业数": int(data["行业名称"].nunique())}


def 运行():
    report = {"通过": False, "步骤": []}
    current = 审计行业台账(WORKBOOK)
    report["步骤"].append({"名称": "v3当前台账审计", **{k: v for k, v in current.items() if k != "行业明细"}})

    if not SNAPSHOT.exists():
        report["步骤"].append({"名称": "个股快照", "通过": False, "原因": f"文件不存在: {SNAPSHOT}"})
    else:
        frame = pd.read_csv(SNAPSHOT, dtype=str)
        historical_audit = 审计个股历史基本面(frame)
        HISTORICAL_AUDIT.parent.mkdir(parents=True, exist_ok=True)
        HISTORICAL_AUDIT.write_text(json.dumps(historical_audit, ensure_ascii=False, indent=2), encoding="utf-8")
        report["步骤"].append({"名称": "个股历史基本面审计", **historical_audit, "报告": str(HISTORICAL_AUDIT)})
        audit = 审计个股快照(frame)
        report["步骤"].append({"名称": "个股快照审计", **audit})
        if audit["通过"]:
            with open(ROOT / "基本面/个股评分配置.yaml", encoding="utf-8") as source:
                config = yaml.safe_load(source) or {}
            scored = 计算评分(frame, config)
            scored.to_csv(SCORE_OUTPUT, index=False, encoding="utf-8-sig")
            report["步骤"].append({"名称": "个股评分生成", "通过": True, "行数": len(scored), "输出": str(SCORE_OUTPUT)})
            ranked = 生成研究排序(scored)
            ranked.to_csv(RESEARCH_OUTPUT, index=False, encoding="utf-8-sig")
            RESEARCH_AUDIT.parent.mkdir(parents=True, exist_ok=True)
            RESEARCH_AUDIT.write_text(json.dumps(审计研究覆盖率(scored), ensure_ascii=False, indent=2), encoding="utf-8")
            report["步骤"].append({"名称": "当前研究排序生成", "通过": True, "行数": len(ranked), "输出": str(RESEARCH_OUTPUT), "审计": str(RESEARCH_AUDIT)})
            pool = 生成研究池(scored, frame, limit=50)
            pool.to_csv(POOL_OUTPUT, index=False, encoding="utf-8-sig")
            POOL_REPORT.parent.mkdir(parents=True, exist_ok=True)
            POOL_REPORT.write_text(json.dumps(研究池报告(pool), ensure_ascii=False, indent=2), encoding="utf-8")
            report["步骤"].append({"名称": "基本面研究池生成", "通过": True, "行数": len(pool), "入选数量": int(pool["入选研究池"].sum()), "输出": str(POOL_OUTPUT), "报告": str(POOL_REPORT)})
        else:
            report["步骤"].append({"名称": "个股评分生成", "通过": False, "原因": "个股快照审计未通过"})

    if INDUSTRY_INPUT.exists() and not current.get("有发布日期数", 0) == 0:
        command = [sys.executable, str(ROOT / "基本面/构建行业景气历史评分.py")]
        process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        report["步骤"].append({"名称": "行业历史评分生成", "通过": process.returncode == 0, "输出": process.stdout.strip(), "错误": process.stderr.strip()})
    else:
        report["步骤"].append({"名称": "行业历史评分生成", "通过": False, "原因": "v3指标没有发布日期，不能安全生成历史行业评分"})

    ready, detail = _industry_history_ready()
    report["步骤"].append({"名称": "行业历史评分审计", "通过": ready, **detail})
    score_ready = SCORE_OUTPUT.exists() and not pd.read_csv(SCORE_OUTPUT).empty
    report["联合模块可启用"] = bool(ready and score_ready)
    report["通过"] = report["联合模块可启用"]
    report["说明"] = "数据未齐全时保持联合模块关闭；不使用当前值回填历史。"
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    result = 运行()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["通过"] else 1)


if __name__ == "__main__":
    main()
