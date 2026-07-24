#!/usr/bin/env python3
"""使用Optuna优化多股票策略，严格分离训练期与验证期。"""

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

import optuna
import yaml


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
配置文件列表 = [
    "买入信号配置.yaml",
    "卖出规则配置.yaml",
    "仓位配置.yaml",
    "参数配置.yaml",
    "过滤因子配置.yaml",
    "因子配置.yaml",
    "核心模块配置.yaml",
]


def 读取yaml(path):
    with open(path, encoding="utf-8") as source:
        return yaml.safe_load(source)


def 保存yaml(path, data):
    with open(path, "w", encoding="utf-8") as target:
        yaml.safe_dump(data, target, allow_unicode=True, sort_keys=False)


def 配置交易成本指纹(config_dir):
    params = 读取yaml(os.path.join(config_dir, "参数配置.yaml"))
    payload = json.dumps(params.get("交易成本", {}), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def 找配置项(items, key, value):
    return next(item for item in items if item.get(key) == value)


def 生成试验配置(base_dir, target_dir, params, capital):
    os.makedirs(target_dir, exist_ok=True)
    for filename in 配置文件列表:
        shutil.copy2(os.path.join(base_dir, filename), os.path.join(target_dir, filename))

    buy = 读取yaml(os.path.join(target_dir, "买入信号配置.yaml"))
    for signal in buy.get("买入信号列表", []):
        signal_key = signal.get("英文标识")
        if signal_key in params:
            signal["启用"] = bool(params[signal_key])
        signal["单笔买入上限"] = round(capital * params["单笔买入上限比例"], 2)
    保存yaml(os.path.join(target_dir, "买入信号配置.yaml"), buy)

    filters = 读取yaml(os.path.join(target_dir, "过滤因子配置.yaml"))
    rsi_ma = 找配置项(filters["过滤因子列表"], "英文标识", "rsi_ma_filter")
    rsi_ma["启用"] = bool(params["启用RSI_MA过滤"])
    rsi_ma["检查K线数"] = int(params["RSI_MA检查K线数"])
    ma_direction = 找配置项(filters["过滤因子列表"], "英文标识", "ma_direction_filter")
    ma_direction["启用"] = bool(params["启用MA方向过滤"])
    ma_direction["过滤模式"] = "斜率拦截"
    threshold = float(params["MA对称斜率阈值"])
    ma_direction["斜率下阈值"] = -threshold
    ma_direction["斜率上阈值"] = threshold
    保存yaml(os.path.join(target_dir, "过滤因子配置.yaml"), filters)

    sell = 读取yaml(os.path.join(target_dir, "卖出规则配置.yaml"))
    atr = 找配置项(sell["卖出条件列表"], "英文标识", "atr_trailing")
    atr["启用"] = True
    atr["ATR倍数"] = float(params["ATR倍数"])
    保存yaml(os.path.join(target_dir, "卖出规则配置.yaml"), sell)

    position = 读取yaml(os.path.join(target_dir, "仓位配置.yaml"))
    position["基准仓位"]["基础单只金额"] = round(capital * params["单笔买入上限比例"], 2)
    position["基准仓位"]["最大单只比例"] = float(params["单笔买入上限比例"])
    保存yaml(os.path.join(target_dir, "仓位配置.yaml"), position)


def 调用回测(config_dir, stocks, start, end, capital, liquidity_limit, workers):
    command = [
        sys.executable,
        os.path.join(项目根目录, "运行程序", "run_backtest.py"),
        "--config", config_dir,
        "--stocks", stocks,
        "--start", start,
        "--end", end,
        "--capital", str(capital),
        "--liquidity-limit", str(liquidity_limit),
        "--workers", str(workers),
    ]
    completed = subprocess.run(
        command,
        cwd=项目根目录,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def 建议参数(trial, round_no):
    return {
        "rsi_cross_20": trial.suggest_categorical("rsi_cross_20", [True, False]),
        "rsi_cross_30": trial.suggest_categorical("rsi_cross_30", [True, False]),
        "rsi_cross_ma": trial.suggest_categorical("rsi_cross_ma", [True, False]),
        "rsi_cross_70": trial.suggest_categorical("rsi_cross_70", [True, False]),
        "启用RSI_MA过滤": trial.suggest_categorical("启用RSI_MA过滤", [True, False]),
        "启用MA方向过滤": trial.suggest_categorical("启用MA方向过滤", [True, False]),
        "RSI_MA检查K线数": trial.suggest_int("RSI_MA检查K线数", 2, 10),
        "MA对称斜率阈值": trial.suggest_float("MA对称斜率阈值", 0.3, 3.0),
        "单笔买入上限比例": trial.suggest_float("单笔买入上限比例", 0.05, 0.20),
        "ATR倍数": trial.suggest_float("ATR倍数", 1.5, 4.0),
    }


def 局部网格参数(best_params):
    """围绕当前最佳点生成MA阈值×ATR倍数的3×3局部网格。"""
    ma_center = float(best_params["MA对称斜率阈值"])
    atr_center = float(best_params["ATR倍数"])
    ma_values = sorted({max(0.3, min(3.0, ma_center + offset)) for offset in (-0.3, 0.0, 0.3)})
    atr_values = sorted({max(1.5, min(4.0, atr_center + offset)) for offset in (-0.3, 0.0, 0.3)})
    return [
        {
            "rsi_cross_20": bool(best_params["rsi_cross_20"]),
            "rsi_cross_30": bool(best_params["rsi_cross_30"]),
            "rsi_cross_ma": bool(best_params["rsi_cross_ma"]),
            "rsi_cross_70": bool(best_params["rsi_cross_70"]),
            "启用RSI_MA过滤": bool(best_params["启用RSI_MA过滤"]),
            "启用MA方向过滤": bool(best_params["启用MA方向过滤"]),
            "RSI_MA检查K线数": int(best_params["RSI_MA检查K线数"]),
            "MA对称斜率阈值": ma_value,
            "单笔买入上限比例": float(best_params["单笔买入上限比例"]),
            "ATR倍数": atr_value,
        }
        for ma_value in ma_values
        for atr_value in atr_values
    ]


def 写试验CSV(study, path):
    names = sorted({key for trial in study.trials for key in trial.params})
    metric_names = ["平均年化收益率", "平均最大回撤", "加权胜率", "平均盈亏比", "总交易数"]
    fields = ["试验号", "状态", "综合得分"] + metric_names + names
    with open(path, "w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        for trial in study.trials:
            row = {"试验号": trial.number, "状态": trial.state.name, "综合得分": trial.value}
            summary = trial.user_attrs.get("训练汇总", {})
            row.update({name: summary.get(name) for name in metric_names})
            row.update(trial.params)
            writer.writerow(row)


def 分布统计(details, field):
    values = sorted(item[field] for item in details if "错误" not in item)
    if not values:
        return {"最小": None, "中位数": None, "最大": None}
    middle = len(values) // 2
    median = values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2
    return {"最小": values[0], "中位数": median, "最大": values[-1]}


def 写中文报告(path, round_no, train_report, validation_report, best_params, threshold):
    train = train_report["汇总"]
    validation = validation_report["汇总"]
    returns = 分布统计(validation_report["股票明细"], "总收益率")
    drawdowns = 分布统计(validation_report["股票明细"], "最大回撤")
    lines = [
        f"# 自动优化第{round_no}轮报告",
        "",
        "## 数据隔离",
        "",
        f"- 训练期：{train_report['开始日期']} 至 {train_report['结束日期']}，Optuna只使用训练期综合得分。",
        f"- 验证期：{validation_report['开始日期']} 至 {validation_report['结束日期']}，仅在全部训练搜索结束并选定唯一候选后评估一次。",
        "- 交易成本保持正式配置不变；单笔金额不超过上一交易日成交额的1%。",
        "",
        "## 最佳参数",
        "",
        "```yaml",
        yaml.safe_dump(best_params, allow_unicode=True, sort_keys=False).strip(),
        "```",
        "",
        "## 核心结果",
        "",
        f"- 训练期综合得分：{train.get('综合得分', 0):.4f}",
        f"- 验证期综合得分：{validation.get('综合得分', 0):.4f}",
        f"- 达标线：{threshold:.2f}；结果：{'达标' if validation.get('综合得分', -999) > threshold else '未达标'}",
        f"- 验证期平均年化收益率：{validation.get('平均年化收益率', 0):.2%}",
        f"- 验证期平均最大回撤：{validation.get('平均最大回撤', 0):.2%}",
        f"- 验证期加权胜率：{validation.get('加权胜率', 0):.2%}",
        f"- 验证期平均盈亏比：{validation.get('平均盈亏比', 0):.3f}",
        "",
        "## 股票分布",
        "",
        f"- 收益率：最小 {returns['最小']:.2%} / 中位数 {returns['中位数']:.2%} / 最大 {returns['最大']:.2%}",
        f"- 最大回撤：最小 {drawdowns['最小']:.2%} / 中位数 {drawdowns['中位数']:.2%} / 最大 {drawdowns['最大']:.2%}",
    ]
    with open(path, "w", encoding="utf-8") as target:
        target.write("\n".join(lines) + "\n")


def 写轮次训练报告(path, round_no, train_report, best_params):
    """每轮只写训练结果；验证数据必须等全部搜索结束后才读取。"""
    train = train_report["汇总"]
    returns = 分布统计(train_report["股票明细"], "总收益率")
    drawdowns = 分布统计(train_report["股票明细"], "最大回撤")
    lines = [
        f"# 自动优化第{round_no}轮训练报告", "", "## 数据隔离", "",
        f"- 训练期：{train_report['开始日期']} 至 {train_report['结束日期']}。",
        "- 本轮未读取验证集；验证集只在所有训练搜索和全量训练复核结束后读取一次。",
        "- 交易成本保持正式配置不变；流动性上限保持上一交易日成交额的1%。", "",
        "## 本轮最佳参数", "", "```yaml",
        yaml.safe_dump(best_params, allow_unicode=True, sort_keys=False).strip(),
        "```", "", "## 训练结果", "",
        f"- 综合得分：{train.get('综合得分', -999):.4f}",
        f"- 平均年化收益率：{train.get('平均年化收益率', 0):.2%}",
        f"- 平均最大回撤：{train.get('平均最大回撤', 0):.2%}",
        f"- 加权胜率：{train.get('加权胜率', 0):.2%}",
        f"- 平均盈亏比：{train.get('平均盈亏比', 0):.3f}",
        f"- 股票收益分布：最小 {returns['最小']:.2%} / 中位数 {returns['中位数']:.2%} / 最大 {returns['最大']:.2%}",
        f"- 股票最大回撤分布：最小 {drawdowns['最小']:.2%} / 中位数 {drawdowns['中位数']:.2%} / 最大 {drawdowns['最大']:.2%}",
    ]
    with open(path, "w", encoding="utf-8") as target:
        target.write("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description="策略0717 Optuna自动优化")
    parser.add_argument("--stocks", default="数据模块/hs300_list.txt")
    parser.add_argument("--full-stocks", default="数据模块/hs300_list.txt")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--trials", type=int, default=200)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--capital", type=float, default=20_000_000)
    parser.add_argument("--liquidity-limit", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=20260721)
    parser.add_argument("--workers", type=int, default=max(1, min(8, os.cpu_count() or 1)))
    parser.add_argument("--experiment-dir", help="指定已有或新实验目录，用于断点续跑")
    parser.add_argument("--train-start", default="2020-01-01")
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--validation-start", default="2024-01-01")
    parser.add_argument("--validation-end", default="2026-07-01")
    args = parser.parse_args()
    if args.trials < 1 or args.rounds < 1:
        parser.error("trials和rounds必须大于0")
    if args.rounds > args.trials:
        parser.error("rounds不能超过总试验数trials")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_dir = os.path.abspath(args.experiment_dir) if args.experiment_dir else os.path.join(
        项目根目录, "10_实验记录", f"自动优化_{timestamp}"
    )
    os.makedirs(experiment_dir, exist_ok=True)
    base_config = os.path.join(项目根目录, "1_策略配置")
    cost_fingerprint = 配置交易成本指纹(base_config)
    search_candidates = []

    for round_no in range(1, args.rounds + 1):
        round_budget = args.trials // args.rounds + (1 if round_no <= args.trials % args.rounds else 0)
        round_dir = os.path.join(experiment_dir, f"第{round_no}轮")
        os.makedirs(round_dir, exist_ok=True)
        storage = f"sqlite:///{os.path.join(round_dir, 'optuna.db')}"
        study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=args.seed + round_no),
            storage=storage,
            study_name=f"strategy0717_round_{round_no}",
            load_if_exists=True,
        )

        def objective(trial):
            try:
                params = 建议参数(trial, round_no)
                with tempfile.TemporaryDirectory(prefix="strategy0717_trial_") as config_dir:
                    生成试验配置(base_config, config_dir, params, args.capital)
                    if 配置交易成本指纹(config_dir) != cost_fingerprint:
                        raise RuntimeError("交易成本配置被修改，试验终止")
                    report = 调用回测(
                        config_dir, args.stocks, args.train_start, args.train_end,
                        args.capital, args.liquidity_limit, args.workers,
                    )
                trial.set_user_attr("训练汇总", report["汇总"])
                return float(report["汇总"].get("综合得分", -999.0))
            except Exception as error:
                trial.set_user_attr("错误", str(error))
                return -999.0

        remaining = max(0, round_budget - len(study.trials))
        if remaining:
            state = {"best": study.best_value if study.best_trials else -999.0, "stagnant": 0, "grid_round": 0}

            def callback(current_study, completed_trial):
                if completed_trial.value is not None and completed_trial.value > state["best"] + 1e-12:
                    state["best"] = completed_trial.value
                    state["stagnant"] = 0
                    return
                state["stagnant"] += 1
                if state["stagnant"] < 10:
                    return
                state["stagnant"] = 0
                state["grid_round"] += 1
                for params in 局部网格参数(current_study.best_params):
                    current_study.enqueue_trial(params, user_attrs={
                        "来源": f"连续10次无提升后的局部网格{state['grid_round']}"
                    })

            study.optimize(objective, n_trials=remaining, gc_after_trial=True, callbacks=[callback])

        best_params = dict(study.best_trial.params)
        with tempfile.TemporaryDirectory(prefix="strategy0717_best_") as config_dir:
            生成试验配置(base_config, config_dir, best_params, args.capital)
            train_report = 调用回测(
                config_dir, args.stocks, args.train_start, args.train_end,
                args.capital, args.liquidity_limit, args.workers,
            )
            shutil.copytree(config_dir, os.path.join(round_dir, "最佳配置"), dirs_exist_ok=True)

        with open(os.path.join(round_dir, "训练期结果.json"), "w", encoding="utf-8") as target:
            json.dump(train_report, target, ensure_ascii=False, indent=2)
        写轮次训练报告(
            os.path.join(round_dir, "中文训练报告.md"), round_no,
            train_report, best_params,
        )
        写试验CSV(study, os.path.join(round_dir, "全部试验.csv"))
        for trial in study.trials:
            if trial.state == optuna.trial.TrialState.COMPLETE and trial.value is not None:
                search_candidates.append({
                    "轮次": round_no,
                    "试验号": trial.number,
                    "预筛选训练得分": float(trial.value),
                    "参数": dict(trial.params),
                })
        print(f"第{round_no}轮：训练={study.best_value:.4f}")

    # 先按预筛选训练分取全局前K名，再用完整沪深300训练期重新排名。
    unique_candidates = []
    seen_params = set()
    for candidate in sorted(search_candidates, key=lambda item: item["预筛选训练得分"], reverse=True):
        signature = json.dumps(candidate["参数"], sort_keys=True, ensure_ascii=False)
        if signature in seen_params:
            continue
        seen_params.add(signature)
        unique_candidates.append(candidate)
        if len(unique_candidates) >= args.top_k:
            break

    rerank_dir = os.path.join(experiment_dir, "全量训练复核")
    os.makedirs(rerank_dir, exist_ok=True)
    reranked = []
    for index, candidate in enumerate(unique_candidates, 1):
        candidate_dir = os.path.join(rerank_dir, f"候选{index:02d}")
        config_dir = os.path.join(candidate_dir, "配置")
        生成试验配置(base_config, config_dir, candidate["参数"], args.capital)
        full_train_report = 调用回测(
            config_dir, args.full_stocks, args.train_start, args.train_end,
            args.capital, args.liquidity_limit, args.workers,
        )
        with open(os.path.join(candidate_dir, "沪深300训练期结果.json"), "w", encoding="utf-8") as target:
            json.dump(full_train_report, target, ensure_ascii=False, indent=2)
        candidate = dict(candidate)
        candidate["沪深300训练得分"] = float(full_train_report["汇总"].get("综合得分", -999.0))
        candidate["配置目录"] = config_dir
        candidate["训练报告"] = full_train_report
        reranked.append(candidate)
        print(
            f"全量复核候选{index}/{len(unique_candidates)}："
            f"预筛选={candidate['预筛选训练得分']:.4f}，"
            f"沪深300训练={candidate['沪深300训练得分']:.4f}"
        )

    with open(os.path.join(rerank_dir, "候选排名.csv"), "w", encoding="utf-8-sig", newline="") as target:
        fields = ["全量排名", "来源轮次", "试验号", "预筛选训练得分", "沪深300训练得分", "参数JSON"]
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        for rank, candidate in enumerate(
            sorted(reranked, key=lambda item: item["沪深300训练得分"], reverse=True), 1
        ):
            writer.writerow({
                "全量排名": rank,
                "来源轮次": candidate["轮次"],
                "试验号": candidate["试验号"],
                "预筛选训练得分": candidate["预筛选训练得分"],
                "沪深300训练得分": candidate["沪深300训练得分"],
                "参数JSON": json.dumps(candidate["参数"], ensure_ascii=False, sort_keys=True),
            })

    # 完整沪深300训练期选出唯一候选后，验证集只使用一次。
    winner = max(reranked, key=lambda item: item["沪深300训练得分"])
    final_dir = os.path.join(experiment_dir, "最终候选")
    os.makedirs(final_dir, exist_ok=True)
    validation_report = 调用回测(
        winner["配置目录"], args.full_stocks, args.validation_start, args.validation_end,
        args.capital, args.liquidity_limit, args.workers,
    )
    shutil.copytree(winner["配置目录"], os.path.join(final_dir, "最佳配置"), dirs_exist_ok=True)
    with open(os.path.join(final_dir, "训练期结果.json"), "w", encoding="utf-8") as target:
        json.dump(winner["训练报告"], target, ensure_ascii=False, indent=2)
    with open(os.path.join(final_dir, "验证期结果.json"), "w", encoding="utf-8") as target:
        json.dump(validation_report, target, ensure_ascii=False, indent=2)
    写中文报告(
        os.path.join(final_dir, "中文报告.md"), winner["轮次"], winner["训练报告"],
        validation_report, winner["参数"], args.threshold,
    )
    best_validation = float(validation_report["汇总"].get("综合得分", -999.0))
    merged_config = {}
    for filename in 配置文件列表:
        merged_config[filename] = 读取yaml(os.path.join(winner["配置目录"], filename))
    with open(os.path.join(final_dir, "最佳配置_正式版.yaml"), "w", encoding="utf-8") as target:
        yaml.safe_dump(merged_config, target, allow_unicode=True, sort_keys=False)
    print(json.dumps({
        "实验目录": experiment_dir,
        "最终候选来源轮次": winner["轮次"],
        "预筛选训练得分": winner["预筛选训练得分"],
        "沪深300训练得分": winner["沪深300训练得分"],
        "验证得分": best_validation,
        "是否达标": best_validation > args.threshold,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
