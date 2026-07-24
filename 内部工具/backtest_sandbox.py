#!/usr/bin/env python3
"""在单股票上对新过滤因子做隔离A/B验证。"""

import argparse
import json
import os
import shutil
import tempfile
from datetime import datetime

import yaml

from 回测引擎.backtest_engine import 跑回测


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
配置文件列表 = [
    "买入信号配置.yaml", "卖出规则配置.yaml", "仓位配置.yaml",
    "参数配置.yaml", "过滤因子配置.yaml", "因子配置.yaml", "核心模块配置.yaml",
]


def 复制配置(source, target):
    os.makedirs(target, exist_ok=True)
    for filename in 配置文件列表:
        shutil.copy2(os.path.join(source, filename), os.path.join(target, filename))


def 设置成交量过滤(config_dir, enabled, minimum):
    path = os.path.join(config_dir, "过滤因子配置.yaml")
    with open(path, encoding="utf-8") as source:
        config = yaml.safe_load(source)
    item = next(row for row in config["过滤因子列表"] if row["英文标识"] == "volume_spike_filter")
    item["启用"] = enabled
    item["最低成交额比率"] = minimum
    with open(path, "w", encoding="utf-8") as target:
        yaml.safe_dump(config, target, allow_unicode=True, sort_keys=False)


def 摘要(result):
    return {
        "买入次数": result["买入次数"],
        "胜率": result["胜率"],
        "总收益率": result["总收益率"],
        "最大回撤": result["最大回撤"],
        "盈亏比": result["盈亏比"],
    }


def main():
    parser = argparse.ArgumentParser(description="新因子单股票沙箱")
    parser.add_argument("--stock", default="600519")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--minimum", type=float, default=0.70)
    args = parser.parse_args()

    output_dir = os.path.join(
        项目根目录, "10_实验记录", f"单因子_成交量过滤_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(output_dir, exist_ok=True)
    source = os.path.join(项目根目录, "1_策略配置")
    with tempfile.TemporaryDirectory(prefix="sandbox_baseline_") as baseline_dir, tempfile.TemporaryDirectory(prefix="sandbox_factor_") as factor_dir:
        复制配置(source, baseline_dir)
        复制配置(source, factor_dir)
        设置成交量过滤(baseline_dir, False, args.minimum)
        设置成交量过滤(factor_dir, True, args.minimum)
        baseline = 跑回测(
            args.stock, args.start, args.end, 20_000_000,
            配置目录=baseline_dir, 运行参数={"流动性上限比例": 0.01}, 静默=True,
        )
        factor = 跑回测(
            args.stock, args.start, args.end, 20_000_000,
            配置目录=factor_dir, 运行参数={"流动性上限比例": 0.01}, 静默=True,
        )
    report = {"股票": args.stock, "区间": [args.start, args.end], "基线": 摘要(baseline), "启用因子": 摘要(factor)}
    report["变化"] = {
        "交易次数": report["启用因子"]["买入次数"] - report["基线"]["买入次数"],
        "收益率": report["启用因子"]["总收益率"] - report["基线"]["总收益率"],
        "最大回撤": report["启用因子"]["最大回撤"] - report["基线"]["最大回撤"],
    }
    report["是否通过单股验证"] = bool(
        report["变化"]["收益率"] > 0 and report["变化"]["最大回撤"] <= 0
    )
    with open(os.path.join(output_dir, "单因子结果.json"), "w", encoding="utf-8") as target:
        json.dump(report, target, ensure_ascii=False, indent=2)
    with open(os.path.join(output_dir, "单因子归因报告.md"), "w", encoding="utf-8") as target:
        target.write(
            "# 成交量异常放大过滤单因子归因报告\n\n"
            f"- 股票：{args.stock}；区间：{args.start} 至 {args.end}\n"
            f"- 基线：{report['基线']['买入次数']}笔，收益 {report['基线']['总收益率']:+.2f}%，回撤 {report['基线']['最大回撤']:.2f}%\n"
            f"- 启用因子：{report['启用因子']['买入次数']}笔，收益 {report['启用因子']['总收益率']:+.2f}%，回撤 {report['启用因子']['最大回撤']:.2f}%\n"
            f"- 结论：{'通过单股验证，可进入全市场测试' if report['是否通过单股验证'] else '未通过单股验证，不进入全市场测试'}\n"
        )
    print(json.dumps({"输出目录": output_dir, **report}, ensure_ascii=False))


if __name__ == "__main__":
    main()
