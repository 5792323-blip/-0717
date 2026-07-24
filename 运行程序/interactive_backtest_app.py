#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地交互式回测页面：调资金/参数后直接运行回测并查看新报告。"""

import argparse
import copy
import csv
import json
import os
import shutil
import socket
import sys
import uuid
import webbrowser
from collections import Counter
from datetime import datetime

项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 项目根目录)

import yaml
import pandas as pd
from flask import Flask, Response, render_template_string, request, send_from_directory, url_for

from 回测引擎.backtest_engine import 跑回测, 保存结果
from 回测引擎.report_generator import 生成报告
from 运行程序.run_backtest import 读取股票列表 as 读取多股列表, 执行单股任务 as 执行多股任务, 汇总结果 as 汇总多股结果
from 组合回测.共享资金池网格 import replay as 重放共享资金池网格

正式配置目录 = os.path.join(项目根目录, "1_策略配置")
实验记录目录 = os.path.join(项目根目录, "10_实验记录")
输出目录 = os.path.join(项目根目录, "9_输出")
工作台配置路径 = os.path.join(实验记录目录, "当前回测工作台配置.json")
最近回测配置路径 = os.path.join(实验记录目录, "最近一次回测实际配置.json")

应用 = Flask(__name__)
最近报告 = {"token": None, "path": None, "run_dir": None}
最近多股报告 = {"token": None, "path": None, "run_dir": None}
沪深300列表路径 = os.path.join(项目根目录, "数据模块", "hs300_list.txt")


模块显示顺序 = {
    "买入规则": [
        ("rsi_cross_20", "RSI上穿20"), ("rsi_cross_30", "RSI上穿30"),
        ("rsi_cross_ma", "RSI上穿均线"), ("rsi_cross_70", "RSI上穿70"),
    ],
    "卖出规则": [
        ("stagnation_exit", "无效交易退出"), ("take_profit", "分批止盈"),
        ("profit_8_exit", "盈利8%平仓"), ("tb_rsi_low_exit", "TB最低价RSI下穿卖出"),
        ("stop_loss", "硬止损"), ("rsi_guard", "RSI站岗价止损"),
        ("rsi_threshold_hold", "RSI阈值守仓（暂缓ATR）"),
        ("atr_trailing", "ATR跟踪止盈止损"), ("atr_take_profit", "ATR跟踪止盈（仅盈利触发）"),
        ("momentum_exit", "动能衰竭退出"),
        ("time_exit", "时间退出"), ("divergence_fix", "背离修正卖出"),
    ],
    "过滤因子": [
        ("index_trend_filter", "沪深300长期趋势过滤"),
        ("volume_spike_filter", "上一交易日成交额确认"),
        ("market_regime_filter", "沪深300市场状态过滤"),
        ("volatility_regime_filter", "波动率状态过滤"),
        ("alpha_composite_filter", "IC复合扩展因子"), ("ma_direction_filter", "MA方向过滤"),
        ("divergence_filter", "RSI背离过滤"), ("rsi_ma_filter", "RSI_MA假信号过滤"),
        ("quality_score_filter", "信号质量分过滤"), ("consecutive_loss_filter", "连续亏损过滤"),
        ("rsi_position_filter", "RSI位置过滤"), ("rsi_neutral_zone_filter", "RSI中性区过滤"),
        ("rsi_band_alignment_filter", "RSI区间对齐过滤"),
    ],
    "扩展因子": [
        ("market_state", "大盘状态"), ("rsi_ma_filter", "RSI_MA因子"),
        ("divergence", "背离因子"), ("ma_direction", "MA方向因子"),
        ("entry_timing", "K线动量入场"), ("signal_scorer", "信号质量评分"),
        ("momentum_exit", "动能退出因子"), ("take_profit", "止盈因子"),
        ("position_sizing", "动态仓位"), ("total_control", "总仓位控制"),
        ("grid_addon", "网格加仓（实验：固定/线性/倍数）"),
        ("xgboost_trend", "XGBoost趋势"), ("randomforest_market", "RandomForest大盘"),
        ("committee_vote", "委员会投票"), ("ml_entry_timing", "ML入场时机"),
        ("ml_fake_drop", "ML假跌判断"), ("volatility_classifier", "波动率分类器"),
    ],
    "核心模块": [
        ("reverse_price", "反推价计算"), ("sentinel_build", "哨兵价形成"),
        ("sentinel_breakout", "哨兵价突破成交"), ("sentinel_trailing", "哨兵价突破后上移"),
        ("same_bar_entry", "本根形成哨兵价后立即买入"),
        ("next_bar_entry", "下一根K线执行（预计算哨兵价·本根最高价触发）"),
    ],
}

核心旧名对照 = {
    "reverse_price": "反推价计算", "sentinel_build": "哨兵价形成",
    "sentinel_breakout": "哨兵价突破成交", "sentinel_trailing": "哨兵价突破后上移",
    "same_bar_entry": "本根形成立即成交", "next_bar_entry": "下一根执行",
}


页面模板 = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>策略0717 回测页面</title>
  <style>
    :root {
      --bg: #f4efe4;
      --panel: #fffaf1;
      --ink: #1f2937;
      --muted: #6b7280;
      --line: #ded4c2;
      --accent: #0f766e;
      --accent-2: #b45309;
      --danger: #b91c1c;
      --shadow: 0 18px 45px rgba(39, 26, 0, 0.10);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(15, 118, 110, 0.10), transparent 28%),
        radial-gradient(circle at top right, rgba(180, 83, 9, 0.10), transparent 24%),
        linear-gradient(180deg, #f7f2e8 0%, var(--bg) 100%);
    }
    .page {
      display: grid;
      grid-template-columns: minmax(290px, 340px) minmax(0, 1fr);
      min-height: 100vh;
      gap: 14px;
      padding: 14px;
    }
    .panel {
      background: rgba(255, 250, 241, 0.96);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .sidebar {
      padding: 16px;
      position: sticky;
      top: 14px;
      align-self: start;
      max-height: calc(100vh - 28px);
      overflow: auto;
    }
    .content {
      display: grid;
      grid-template-rows: auto auto auto minmax(560px, 1fr);
      gap: 14px;
    }
    .toolbar {
      padding: 16px 20px;
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
    }
    .toolbar-left {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }
    .toolbar-title {
      font-size: 14px;
      color: var(--muted);
    }
    .tab-btn {
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.76);
      color: var(--ink);
      padding: 9px 14px;
      border-radius: 999px;
      font-size: 13px;
      cursor: pointer;
    }
    .tab-btn.active {
      background: linear-gradient(135deg, #0f766e, #115e59);
      color: #fff;
      border-color: #115e59;
    }
    h1 {
      margin: 0 0 6px;
      font-size: 24px;
      line-height: 1.1;
    }
    .subtitle {
      margin: 0 0 14px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }
    .workbench-head {
      margin: 0 0 14px;
      padding: 12px;
      border: 1px solid rgba(15, 118, 110, 0.18);
      border-radius: 18px;
      background: linear-gradient(135deg, rgba(15,118,110,.08), rgba(180,83,9,.06));
    }
    .workbench-head label { margin-bottom: 5px; color: var(--ink); font-weight: 600; }
    .mode-switch { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 10px; }
    .mode-switch button { padding: 9px 8px; border: 1px solid var(--line); background: rgba(255,255,255,.72); color: var(--ink); font-size: 12px; }
    .mode-switch button.active { background: var(--accent); color: #fff; border-color: var(--accent); }
    .mode-section.mode-hidden { display: none; }
    .effective-config { margin-top: 10px; padding: 9px 10px; border-radius: 12px; background: rgba(255,255,255,.62); color: var(--muted); font-size: 11px; line-height: 1.55; }
    .effective-config b { color: var(--ink); }
    .section {
      margin: 0 0 12px;
      padding: 12px;
      background: rgba(255,255,255,0.55);
      border: 1px solid rgba(222, 212, 194, 0.8);
      border-radius: 18px;
    }
    .section h2 {
      margin: 0 0 12px;
      font-size: 15px;
      color: var(--accent-2);
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 10px;
    }
    .mode-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 12px;
    }
    .mode-badge {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
      background: rgba(15, 118, 110, 0.10);
      color: var(--accent);
    }
    label {
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 6px;
    }
    input[type="text"],
    textarea,
    input[type="date"],
    input[type="number"],
    select {
      width: 100%;
      padding: 9px 10px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #fffdfa;
      color: var(--ink);
      font-size: 13px;
    }
    textarea {
      min-height: 76px;
      resize: vertical;
    }
    .checklist {
      display: grid;
      gap: 8px;
    }
    .checkbox {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 10px;
      border: 1px solid rgba(222, 212, 194, 0.8);
      border-radius: 12px;
      background: rgba(255,255,255,0.7);
      color: var(--ink);
      font-size: 13px;
    }
    .checkbox input { width: 16px; height: 16px; }
    .checkbox.disabled { opacity: 0.52; cursor: not-allowed; }
    .module-status {
      margin-left: auto;
      padding: 2px 7px;
      border-radius: 999px;
      background: rgba(15, 118, 110, 0.10);
      color: var(--accent);
      font-size: 10px;
      white-space: nowrap;
    }
    .checkbox.disabled .module-status {
      background: rgba(107, 114, 128, 0.12);
      color: var(--muted);
    }
    .module-card {
      border: 1px solid rgba(222, 212, 194, 0.8);
      border-radius: 12px;
      background: rgba(255,255,255,0.7);
      overflow: hidden;
    }
    .module-card .checkbox {
      border: 0;
      border-radius: 0;
      background: transparent;
    }
    .module-params {
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
      padding: 0 10px 10px 36px;
    }
    .param-row {
      display: grid;
      grid-template-columns: minmax(88px, 0.9fr) minmax(0, 1.2fr);
      gap: 8px;
      align-items: center;
    }
    .param-row label {
      margin: 0;
      color: var(--muted);
      font-size: 11px;
      line-height: 1.35;
    }
    .param-row input,
    .param-row textarea {
      min-height: 30px;
      padding: 6px 8px;
      border-radius: 8px;
      font-size: 12px;
      background: rgba(255,255,255,0.86);
    }
    .param-row textarea {
      min-height: 54px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .param-bool {
      justify-self: start;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: var(--ink);
      font-size: 12px;
    }
    .param-bool input { width: 15px; height: 15px; }
    .param-note {
      padding: 0 10px 10px 36px;
      color: var(--muted);
      font-size: 11px;
      line-height: 1.45;
    }
    .config-fold {
      margin-top: 10px;
      border: 1px solid rgba(222, 212, 194, 0.9);
      border-radius: 14px;
      background: rgba(255,255,255,0.46);
      overflow: hidden;
    }
    .config-fold summary {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 10px 12px;
      cursor: pointer;
      color: var(--ink);
      font-size: 13px;
      font-weight: 600;
      list-style: none;
    }
    .config-fold summary::-webkit-details-marker { display: none; }
    .config-fold summary::after { content: "＋"; color: var(--accent); }
    .config-fold[open] summary::after { content: "－"; }
    .fold-body { padding: 0 10px 10px; }
    .fold-count { color: var(--muted); font-size: 11px; font-weight: 400; }
    .compact-note { margin: 8px 2px 0; color: var(--muted); font-size: 11px; line-height: 1.5; }
    .actions {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-top: 18px;
    }
    .action-wide {
      grid-column: 1 / -1;
    }
    button {
      border: 0;
      border-radius: 999px;
      padding: 12px 18px;
      font-size: 14px;
      cursor: pointer;
    }
    .primary {
      background: linear-gradient(135deg, #0f766e, #115e59);
      color: white;
      flex: 1;
    }
    .secondary {
      background: rgba(255,255,255,0.85);
      color: var(--ink);
      border: 1px solid var(--line);
    }
    .status, .metrics, .report-shell {
      padding: 16px 18px;
    }
    .result-card {
      padding: 16px 18px;
    }
    .status {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      padding: 8px 12px;
      background: rgba(15, 118, 110, 0.10);
      color: var(--accent);
      font-size: 13px;
    }
    .error {
      color: var(--danger);
      background: rgba(185, 28, 28, 0.08);
    }
    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }
    .metric {
      padding: 16px;
      border-radius: 16px;
      background: rgba(255,255,255,0.72);
      border: 1px solid rgba(222, 212, 194, 0.8);
    }
    .metric strong {
      display: block;
      font-size: 24px;
      margin-top: 8px;
    }
    .metric span {
      color: var(--muted);
      font-size: 12px;
    }
    .result-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }
    .result-box {
      padding: 14px 16px;
      border-radius: 16px;
      background: rgba(255,255,255,0.72);
      border: 1px solid rgba(222, 212, 194, 0.8);
    }
    .result-box strong {
      display: block;
      font-size: 20px;
      margin-top: 6px;
    }
    .result-table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 14px;
      font-size: 13px;
    }
    .result-table th,
    .result-table td {
      text-align: left;
      padding: 9px 10px;
      border-bottom: 1px solid rgba(222, 212, 194, 0.8);
    }
    .result-table th {
      color: var(--muted);
      font-weight: 600;
    }
    .result-note {
      margin-top: 12px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.6;
    }
    .diagnostic-headline {
      margin-top: 12px;
      padding: 10px 12px;
      border-radius: 10px;
      background: rgba(180, 83, 9, 0.09);
      color: var(--accent-2);
      line-height: 1.5;
    }
    .diagnostic-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
      margin-top: 12px;
    }
    .diagnostic-item {
      padding: 10px 12px;
      border: 1px solid rgba(222, 212, 194, 0.8);
      border-radius: 10px;
      background: rgba(255,255,255,0.58);
    }
    .diagnostic-item span { display: block; color: var(--muted); font-size: 11px; }
    .diagnostic-item strong { display: block; margin-top: 4px; font-size: 18px; }
    .diagnostic-table { margin-top: 12px; }
    .diagnostic-warnings { margin-top: 12px; color: var(--danger); font-size: 12px; line-height: 1.7; }
    @media (max-width: 900px) { .diagnostic-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    .section-title {
      font-size: 14px;
      font-weight: 700;
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 10px;
    }
    .config-summary-row {
      display: grid;
      grid-template-columns: 145px minmax(0, 1fr);
      gap: 10px;
      padding: 8px 0;
      border-bottom: 1px solid rgba(222, 212, 194, 0.8);
      font-size: 12px;
    }
    .config-summary-row span:first-child { color: var(--muted); }
    .config-summary-row span:last-child { overflow-wrap: anywhere; }
    iframe {
      width: 100%;
      min-height: 800px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: white;
    }
    .viewer-frame.hidden {
      display: none;
    }
    .viewer-empty {
      padding: 28px 12px;
      text-align: center;
      color: var(--muted);
      font-size: 13px;
    }
    .hint {
      margin-top: 10px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.6;
    }
    .path {
      font-size: 12px;
      color: var(--muted);
      word-break: break-all;
    }
    @media (max-width: 1280px) {
      .page { grid-template-columns: 1fr; }
      .sidebar { position: static; max-height: none; }
      .metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 720px) {
      .grid, .metrics-grid { grid-template-columns: 1fr; }
      .page { padding: 12px; }
      .sidebar, .status, .metrics, .report-shell { padding: 16px; }
    }
  </style>
</head>
<body>
  <div class="page">
<form class="panel sidebar" method="post">
      <h1>回测主页面</h1>
      <p class="subtitle">先选择回测模式和方案，再设置对应参数。两种模式相互独立，保存和运行不会互相覆盖。</p>
      <input type="hidden" name="ui_mode" id="uiMode" value="multi">
      <div class="workbench-head">
        <label for="strategyPreset">策略方案</label>
        <select id="strategyPreset">
          <option value="standard_grid">标准共享网格（推荐）</option>
          <option value="conservative_grid">稳健共享网格</option>
          <option value="independent_legacy">等额独立资金池（旧逻辑对照）</option>
          <option value="custom">自定义参数</option>
        </select>
        <div class="mode-switch" role="tablist" aria-label="回测模式">
          <button type="button" data-mode-tab="multi" class="active">多股组合回测</button>
          <button type="button" data-mode-tab="single">单股回测</button>
        </div>
        <div class="effective-config" id="effectiveConfig"><b>当前方案：</b>标准共享网格 · 1000万组合资金 · 单股上限30万 · 总仓位80% · 现金底线20%</div>
      </div>

      <div class="section mode-section" data-mode-section="single">
        <div class="mode-head">
          <h2>单股模式</h2>
          <span class="mode-badge">独立设置</span>
        </div>
        <div class="grid">
          <div>
            <label>股票代码</label>
            <input type="text" name="single_stock" value="{{ form.single_stock }}">
          </div>
        </div>
        <details class="config-fold">
          <summary><span>① 回测范围、资金与基础指标</span><span class="fold-count">资金 · 日期 · 仓位 · RSI · ATR</span></summary>
          <div class="fold-body grid">
          <label class="checkbox" style="margin: 0 0 12px;">
            <input type="checkbox" name="single_full_position_mode" {% if form.single_full_position_mode %}checked{% endif %}>
            <span>单股满仓模式</span>
            <span class="module-status">自动归一为全仓参数，适合挑战个股基准</span>
          </label>
          <div>
            <label>初始资金</label>
            <input type="number" step="10000" name="single_capital" value="{{ form.single_capital }}">
          </div>
          <div>
            <label>开始日期</label>
            <input type="date" name="single_start" value="{{ form.single_start }}">
          </div>
          <div>
            <label>结束日期</label>
            <input type="date" name="single_end" value="{{ form.single_end }}">
          </div>
          <div>
            <label>基础单只金额</label>
            <input type="number" step="10000" name="single_base_position" value="{{ form.single_base_position }}">
          </div>
          <div>
            <label>最大持仓数</label>
            <input type="number" step="1" name="single_max_positions" value="{{ form.single_max_positions }}">
          </div>
          <div>
            <label>最大单只比例</label>
            <input type="number" step="0.01" name="single_max_single_ratio" value="{{ form.single_max_single_ratio }}">
          </div>
          <div>
            <label>最大总仓位</label>
            <input type="number" step="0.01" name="single_max_total_ratio" value="{{ form.single_max_total_ratio }}">
          </div>
          <div>
            <label>现金底线</label>
            <input type="number" step="0.01" name="single_cash_floor" value="{{ form.single_cash_floor }}">
          </div>
          <div>
            <label>买入流动性上限比例</label>
            <input type="number" step="0.001" name="single_liquidity_limit" value="{{ form.single_liquidity_limit }}">
          </div>
          <div>
            <label>RSI周期</label>
            <input type="number" step="1" name="single_rsi_period" value="{{ form.single_rsi_period }}">
          </div>
          <div>
            <label>RSI价格源</label>
            <select name="single_rsi_price_source">
              <option value="high" {% if form.single_rsi_price_source == 'high' %}selected{% endif %}>最高价RSI（TB买入思路）</option>
              <option value="close" {% if form.single_rsi_price_source == 'close' %}selected{% endif %}>收盘价RSI（当前基线）</option>
              <option value="low" {% if form.single_rsi_price_source == 'low' %}selected{% endif %}>最低价RSI</option>
            </select>
          </div>
          <div>
            <label>买入时机</label>
            <select name="single_entry_timing">
              <option value="precomputed_stop_entry" {% if form.single_entry_timing == 'precomputed_stop_entry' %}selected{% endif %}>严格预挂单（推荐）</option>
              <option value="close_confirm_next_open" {% if form.single_entry_timing == 'close_confirm_next_open' %}selected{% endif %}>收盘确认后次根开盘</option>
              <option value="tb_replay" {% if form.single_entry_timing == 'tb_replay' %}selected{% endif %}>TB复刻模式（最高价RSI同根对照）</option>
              <option value="same_bar_entry" {% if form.single_entry_timing in ('same_bar_entry', 'legacy_same_bar_lookahead', 'intrabar_breakout') %}selected{% endif %}>本根形成哨兵价后立即买入（无前视）</option>
            </select>
          </div>
          <div>
            <label>网格加仓模式（实验）</label>
            <select name="single_grid_mode">
              <option value="fixed_tranche" {% if form.single_grid_mode == 'fixed_tranche' %}selected{% endif %}>固定分层（实验）</option>
              <option value="linear" {% if form.single_grid_mode == 'linear' %}selected{% endif %}>线性递增（实验）</option>
              <option value="multiplier" {% if form.single_grid_mode == 'multiplier' %}selected{% endif %}>倍数加仓（实验）</option>
            </select>
          </div>
          <div>
            <label>首次开仓占网格预算比例</label>
            <input type="number" step="0.01" min="0.01" max="1" name="single_grid_initial_ratio" value="{{ form.single_grid_initial_ratio }}">
          </div>
          <div>
            <label>固定分层每层比例</label>
            <input type="number" step="0.01" min="0.01" max="1" name="single_grid_followup_ratio" value="{{ form.single_grid_followup_ratio }}">
          </div>
          <div>
            <label>倍数加仓倍数</label>
            <input type="number" step="0.1" min="1" name="single_grid_multiplier" value="{{ form.single_grid_multiplier }}">
          </div>
          <div>
            <label>RSI均线周期</label>
            <input type="number" step="1" name="single_rsi_ma_period" value="{{ form.single_rsi_ma_period }}">
          </div>
          <div>
            <label>ATR周期</label>
            <input type="number" step="1" name="single_atr_period" value="{{ form.single_atr_period }}">
          </div>
          <div>
            <label>买入溢价</label>
            <input type="number" step="0.0001" name="single_buy_premium" value="{{ form.single_buy_premium }}">
            <p class="compact-note">严格预挂单下，1.001 代表成交价上限上浮 0.1%；若计划价超过当根最高价，系统按当根最高价成交，不会因溢价造成假拦截。</p>
          </div>
          <div>
            <label>滑点</label>
            <input type="number" step="0.0001" name="single_slippage" value="{{ form.single_slippage }}">
          </div>
          <div>
            <label>佣金</label>
            <input type="number" step="0.00001" name="single_commission" value="{{ form.single_commission }}">
          </div>
          <div>
            <label>ATR跟踪倍数</label>
            <input type="number" step="0.1" name="single_atr_exit_multiple" value="{{ form.single_atr_exit_multiple }}">
          </div>
          <div>
            <label>硬止损倍数</label>
            <input type="number" step="0.1" name="single_hard_stop_multiple" value="{{ form.single_hard_stop_multiple }}">
          </div>
          <div>
            <label>时间退出K线数</label>
            <input type="number" step="1" name="single_time_exit_bars" value="{{ form.single_time_exit_bars }}">
          </div>
          <div>
            <label>时间退出亏损线</label>
            <input type="number" step="0.01" name="single_time_exit_loss" value="{{ form.single_time_exit_loss }}">
          </div>
          </div>
        </details>
        <details class="config-fold">
          <summary><span>⑤ 成交成本与退出参数</span><span class="fold-count">成本 · 止盈 · 时间退出 · 缓冲</span></summary>
          <div class="fold-body grid">
            <div><label>信号过期K线数（兼容保留，当前不自动释放）</label><input type="number" step="1" name="single_signal_expiry_bars" value="{{ form.single_signal_expiry_bars }}"></div>
            <div><label>印花税</label><input type="number" step="0.00001" name="single_stamp_tax" value="{{ form.single_stamp_tax }}"></div>
            <div><label>过户费</label><input type="number" step="0.000001" name="single_transfer_fee" value="{{ form.single_transfer_fee }}"></div>
            <div><label>分批止盈第一档</label><input type="number" step="0.01" name="single_take_profit_1" value="{{ form.single_take_profit_1 }}"></div>
            <div><label>分批止盈第二档</label><input type="number" step="0.01" name="single_take_profit_2" value="{{ form.single_take_profit_2 }}"></div>
            <div><label>分批止盈第三档</label><input type="number" step="0.01" name="single_take_profit_3" value="{{ form.single_take_profit_3 }}"></div>
            <div><label>站岗价ATR缓冲</label><input type="number" step="0.1" name="single_guard_atr_buffer" value="{{ form.single_guard_atr_buffer }}"></div>
            <div><label>动能衰竭基础阈值</label><input type="number" step="1" name="single_momentum_decline" value="{{ form.single_momentum_decline }}"></div>
          </div>
          <p class="compact-note">核心版本：{{ form.single_core_version }}。参数只写入本次实验快照，不覆盖正式策略。</p>
        </details>
        {% for group in single_module_groups %}
        <details class="config-fold" {% if group.category == '买入规则' %}open{% endif %}>
          <summary><span>{{ group.title }}</span><span class="fold-count">{{ group.modules|length }} 项（{{ group.selected_count }}项）</span></summary>
          <div class="fold-body checklist">
            {% for item in group.modules %}
            <div class="module-card {% if item.disabled %}disabled{% endif %}">
              <label class="checkbox {% if item.disabled %}disabled{% endif %}">
                <input type="checkbox" name="{{ item.name }}" {% if item.enabled %}checked{% endif %} {% if item.disabled %}disabled{% endif %}>
                <span>{{ item.label }}</span><span class="module-status">{{ item.status }}</span>
              </label>
              {% if item.params %}
              <div class="module-params">
                {% for param in item.params %}
                <div class="param-row">
                  <label>{{ param.key }}</label>
                  {% if param.type == 'bool' %}
                  <span class="param-bool"><input type="checkbox" name="{{ param.name }}" {% if param.checked %}checked{% endif %}>启用</span>
                  {% elif param.type == 'yaml' %}
                  <textarea name="{{ param.name }}">{{ param.value }}</textarea>
                  {% else %}
                  <input type="{{ param.type }}" step="{{ param.step }}" name="{{ param.name }}" value="{{ param.value }}">
                  {% endif %}
                </div>
                {% endfor %}
              </div>
              {% else %}
              <div class="param-note">{{ item.param_note }}</div>
              {% endif %}
            </div>
            {% endfor %}
          </div>
        </details>
        {% endfor %}
        <div class="actions">
          <button class="primary action-wide" type="submit" name="run_mode" value="single">运行单股回测</button>
          <button class="secondary action-wide" type="submit" name="save_config" value="1">只保存当前选择</button>
          <button class="secondary action-wide" type="submit" name="apply_tb_single" value="1">应用TB复刻参数</button>
        </div>
      </div>

      <div class="section mode-section" data-mode-section="multi">
        <div class="mode-head">
          <h2>多股模式</h2>
          <span class="mode-badge">独立设置</span>
        </div>
        <details class="config-fold">
          <summary><span>① 回测范围、资金与基础指标</span><span class="fold-count">资金 · 日期 · 仓位 · RSI · ATR</span></summary>
          <div class="fold-body grid">
          <div>
            <label>初始资金</label>
            <input type="number" step="10000" name="multi_capital" value="{{ form.multi_capital }}">
          </div>
          <div>
            <label>多股资金模式</label>
            <select name="multi_portfolio_mode">
              <option value="independent" {% if form.multi_portfolio_mode == 'independent' %}selected{% endif %}>原有：等额独立资金池</option>
              <option value="shared_grid" {% if form.multi_portfolio_mode == 'shared_grid' %}selected{% endif %}>新逻辑：共享资金池网格</option>
            </select>
            <p class="compact-note">共享资金池网格会统一管理组合现金；等额独立资金池仅用于和旧结果对比。切换模式后，下面的仓位参数含义也会随之改变。</p>
          </div>
          <div>
            <label>网格加仓模式（实验）</label>
            <select name="multi_grid_mode">
              <option value="fixed_tranche" {% if form.multi_grid_mode == 'fixed_tranche' %}selected{% endif %}>固定分层（实验）</option>
              <option value="linear" {% if form.multi_grid_mode == 'linear' %}selected{% endif %}>线性递增（实验）</option>
              <option value="multiplier" {% if form.multi_grid_mode == 'multiplier' %}selected{% endif %}>倍数加仓（实验）</option>
            </select>
          </div>
          <div>
            <label>首次开仓占网格预算比例</label>
            <input type="number" step="0.01" min="0.01" max="1" name="multi_grid_initial_ratio" value="{{ form.multi_grid_initial_ratio }}">
          </div>
          <div>
            <label>固定分层每层比例</label>
            <input type="number" step="0.01" min="0.01" max="1" name="multi_grid_followup_ratio" value="{{ form.multi_grid_followup_ratio }}">
          </div>
          <div>
            <label>倍数加仓倍数</label>
            <input type="number" step="0.1" min="1" name="multi_grid_multiplier" value="{{ form.multi_grid_multiplier }}">
          </div>
          <div>
            <label>并行进程数</label>
            <input type="number" step="1" min="1" name="multi_workers" value="{{ form.multi_workers }}">
          </div>
          <div>
            <label>开始日期</label>
            <input type="date" name="multi_start" value="{{ form.multi_start }}">
          </div>
          <div>
            <label>结束日期</label>
            <input type="date" name="multi_end" value="{{ form.multi_end }}">
          </div>
          <div>
            <label>共享模式：单股最大资金上限</label>
            <input type="number" step="10000" name="multi_base_position" value="{{ form.multi_base_position }}">
            <p class="compact-note">共享模式下单只股票的实际资金上限；最终还会受“最大单只比例”限制，取两者较小值。</p>
          </div>
          <div>
            <label>最大持仓数</label>
            <input type="number" step="1" name="multi_max_positions" value="{{ form.multi_max_positions }}">
          </div>
          <div>
            <label>组合：最大单只比例</label>
            <input type="number" step="0.01" name="multi_max_single_ratio" value="{{ form.multi_max_single_ratio }}">
          </div>
          <div>
            <label>组合：最大总仓位</label>
            <input type="number" step="0.01" name="multi_max_total_ratio" value="{{ form.multi_max_total_ratio }}">
          </div>
          <div>
            <label>组合：现金底线</label>
            <input type="number" step="0.01" name="multi_cash_floor" value="{{ form.multi_cash_floor }}">
          </div>
          <div>
            <label>买入流动性上限比例</label>
            <input type="number" step="0.001" name="multi_liquidity_limit" value="{{ form.multi_liquidity_limit }}">
          </div>
          <div>
            <label>RSI周期</label>
            <input type="number" step="1" name="multi_rsi_period" value="{{ form.multi_rsi_period }}">
          </div>
          <div>
            <label>RSI价格源</label>
            <select name="multi_rsi_price_source">
              <option value="high" {% if form.multi_rsi_price_source == 'high' %}selected{% endif %}>最高价RSI（TB买入思路）</option>
              <option value="close" {% if form.multi_rsi_price_source == 'close' %}selected{% endif %}>收盘价RSI（当前基线）</option>
              <option value="low" {% if form.multi_rsi_price_source == 'low' %}selected{% endif %}>最低价RSI</option>
            </select>
          </div>
          <div>
            <label>买入时机</label>
            <select name="multi_entry_timing">
              <option value="precomputed_stop_entry" {% if form.multi_entry_timing == 'precomputed_stop_entry' %}selected{% endif %}>严格预挂单（推荐）</option>
              <option value="close_confirm_next_open" {% if form.multi_entry_timing == 'close_confirm_next_open' %}selected{% endif %}>收盘确认后次根开盘</option>
              <option value="tb_replay" {% if form.multi_entry_timing == 'tb_replay' %}selected{% endif %}>TB复刻模式（最高价RSI同根对照）</option>
              <option value="same_bar_entry" {% if form.multi_entry_timing in ('same_bar_entry', 'legacy_same_bar_lookahead', 'intrabar_breakout') %}selected{% endif %}>本根形成哨兵价后立即买入（无前视）</option>
            </select>
          </div>
          <div>
            <label>RSI均线周期</label>
            <input type="number" step="1" name="multi_rsi_ma_period" value="{{ form.multi_rsi_ma_period }}">
          </div>
          <div>
            <label>ATR周期</label>
            <input type="number" step="1" name="multi_atr_period" value="{{ form.multi_atr_period }}">
          </div>
          <div>
            <label>买入溢价</label>
            <input type="number" step="0.0001" name="multi_buy_premium" value="{{ form.multi_buy_premium }}">
          </div>
          <div>
            <label>滑点</label>
            <input type="number" step="0.0001" name="multi_slippage" value="{{ form.multi_slippage }}">
          </div>
          <div>
            <label>佣金</label>
            <input type="number" step="0.00001" name="multi_commission" value="{{ form.multi_commission }}">
          </div>
          <div>
            <label>ATR跟踪倍数</label>
            <input type="number" step="0.1" name="multi_atr_exit_multiple" value="{{ form.multi_atr_exit_multiple }}">
          </div>
          <div>
            <label>硬止损倍数</label>
            <input type="number" step="0.1" name="multi_hard_stop_multiple" value="{{ form.multi_hard_stop_multiple }}">
          </div>
          <div>
            <label>时间退出K线数</label>
            <input type="number" step="1" name="multi_time_exit_bars" value="{{ form.multi_time_exit_bars }}">
          </div>
          <div>
            <label>时间退出亏损线</label>
            <input type="number" step="0.01" name="multi_time_exit_loss" value="{{ form.multi_time_exit_loss }}">
          </div>
          <div>
            <label>多股股票列表（逗号分隔，留空默认用沪深300本地列表）</label>
            <textarea name="multi_stocks">{{ form.multi_stocks }}</textarea>
          </div>
          </div>
        </details>
        <details class="config-fold">
          <summary><span>⑤ 成交成本与退出参数</span><span class="fold-count">成本 · 止盈 · 时间退出 · 缓冲</span></summary>
          <div class="fold-body grid">
            <div><label>信号过期K线数（兼容保留，当前不自动释放）</label><input type="number" step="1" name="multi_signal_expiry_bars" value="{{ form.multi_signal_expiry_bars }}"></div>
            <div><label>印花税</label><input type="number" step="0.00001" name="multi_stamp_tax" value="{{ form.multi_stamp_tax }}"></div>
            <div><label>过户费</label><input type="number" step="0.000001" name="multi_transfer_fee" value="{{ form.multi_transfer_fee }}"></div>
            <div><label>分批止盈第一档</label><input type="number" step="0.01" name="multi_take_profit_1" value="{{ form.multi_take_profit_1 }}"></div>
            <div><label>分批止盈第二档</label><input type="number" step="0.01" name="multi_take_profit_2" value="{{ form.multi_take_profit_2 }}"></div>
            <div><label>分批止盈第三档</label><input type="number" step="0.01" name="multi_take_profit_3" value="{{ form.multi_take_profit_3 }}"></div>
            <div><label>站岗价ATR缓冲</label><input type="number" step="0.1" name="multi_guard_atr_buffer" value="{{ form.multi_guard_atr_buffer }}"></div>
            <div><label>动能衰竭基础阈值</label><input type="number" step="1" name="multi_momentum_decline" value="{{ form.multi_momentum_decline }}"></div>
          </div>
          <p class="compact-note">核心版本：{{ form.multi_core_version }}。多股参数与单股参数保持独立。</p>
        </details>
        {% for group in multi_module_groups %}
        <details class="config-fold" {% if group.category == '买入规则' %}open{% endif %}>
          <summary><span>{{ group.title }}</span><span class="fold-count">{{ group.modules|length }} 项（{{ group.selected_count }}项）</span></summary>
          <div class="fold-body checklist">
            {% for item in group.modules %}
            <div class="module-card {% if item.disabled %}disabled{% endif %}">
              <label class="checkbox {% if item.disabled %}disabled{% endif %}">
                <input type="checkbox" name="{{ item.name }}" {% if item.enabled %}checked{% endif %} {% if item.disabled %}disabled{% endif %}>
                <span>{{ item.label }}</span><span class="module-status">{{ item.status }}</span>
              </label>
              {% if item.params %}
              <div class="module-params">
                {% for param in item.params %}
                <div class="param-row">
                  <label>{{ param.key }}</label>
                  {% if param.type == 'bool' %}
                  <span class="param-bool"><input type="checkbox" name="{{ param.name }}" {% if param.checked %}checked{% endif %}>启用</span>
                  {% elif param.type == 'yaml' %}
                  <textarea name="{{ param.name }}">{{ param.value }}</textarea>
                  {% else %}
                  <input type="{{ param.type }}" step="{{ param.step }}" name="{{ param.name }}" value="{{ param.value }}">
                  {% endif %}
                </div>
                {% endfor %}
              </div>
              {% else %}
              <div class="param-note">{{ item.param_note }}</div>
              {% endif %}
            </div>
            {% endfor %}
          </div>
        </details>
        {% endfor %}
        <div class="actions">
          <button class="primary action-wide" type="submit" name="run_mode" value="multi">运行多股回测</button>
          <button class="secondary" type="submit" name="save_config" value="1">保存多股参数</button>
          <button class="secondary" type="submit" name="load_last" value="1">恢复上次工作配置</button>
          <button class="secondary" type="submit" name="load_last_run" value="1">恢复上次回测配置</button>
          <button class="secondary" type="submit" name="reset" value="1">恢复正式默认值</button>
        </div>
      </div>

      <p class="hint">单股和多股参数会自动保存为“最近工作配置”，刷新或重启后继续使用；只有点击“恢复正式默认值”才会恢复正式配置。</p>
    </form>

    <div class="content">
      <div class="panel status">
        <div>
          <div class="pill {% if error %}error{% endif %}">{{ status }}</div>
          {% if run_dir %}
          <div class="path">结果目录：{{ run_dir }}</div>
          {% endif %}
        </div>
        {% if report_url %}
        <a class="pill" href="{{ report_url }}" target="_blank">单独打开报告</a>
        {% endif %}
      </div>

      <div class="panel toolbar">
        <div class="toolbar-left">
          <span class="toolbar-title">回测视图</span>
          <button class="tab-btn {% if active_view == 'interactive' %}active{% endif %}" type="button" data-view="interactive">参数回测台</button>
          <button class="tab-btn {% if active_view == 'report' %}active{% endif %}" type="button" data-view="report">最新报告</button>
          <button class="tab-btn {% if active_view == 'multi' %}active{% endif %}" type="button" data-view="multi">多股票回放</button>
          <button class="tab-btn {% if active_view == 'stock' %}active{% endif %}" type="button" data-view="stock">当前单票回放</button>
        </div>
        <div class="path">当前股票：{{ form.stock }}</div>
      </div>

      <div class="panel metrics">
        <div class="metrics-grid">
          <div class="metric"><span>总收益率</span><strong>{{ metrics.total_return }}</strong></div>
          <div class="metric"><span>最大回撤</span><strong>{{ metrics.max_drawdown }}</strong></div>
          <div class="metric"><span>胜率</span><strong>{{ metrics.win_rate }}</strong></div>
          <div class="metric"><span>最终权益</span><strong>{{ metrics.final_equity }}</strong></div>
        </div>
      </div>

      <div class="panel result-card">
        <div class="result-grid">
          <div class="result-box"><span>回测类型</span><strong>{{ backtest_result.mode }}</strong></div>
          <div class="result-box"><span>样本数量</span><strong>{{ backtest_result.sample_count }}</strong></div>
          <div class="result-box"><span>结果文件</span><strong>{{ backtest_result.output_name }}</strong></div>
        </div>
        {% if backtest_result.rows %}
        <table class="result-table">
          <thead>
            <tr>
              <th>项目</th>
              <th>数值</th>
            </tr>
          </thead>
          <tbody>
            {% for row in backtest_result.rows %}
            <tr>
              <td>{{ row.label }}</td>
              <td>{{ row.value }}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
        {% endif %}
        {% if backtest_result.note %}
        <div class="result-note">{{ backtest_result.note }}</div>
        {% endif %}
      </div>

      {% if backtest_result.diagnostics %}
      <div class="panel result-card diagnostics-card">
        <div class="section-title">本次回测成交诊断</div>
        <div class="compact-note">统计来自本次回测的逐根决策记录，不是页面默认值。它把“有信号、价格突破、执行成交、最终拦截”分开显示。</div>
        {% if backtest_result.diagnostics.headline %}
        <div class="diagnostic-headline">最主要原因：<strong>{{ backtest_result.diagnostics.headline }}</strong></div>
        {% endif %}
        <div class="diagnostic-grid">
          {% for item in backtest_result.diagnostics.summary %}
          <div class="diagnostic-item"><span>{{ item.label }}</span><strong>{{ item.value }}</strong></div>
          {% endfor %}
        </div>
        {% if backtest_result.diagnostics.reasons %}
        <table class="result-table diagnostic-table">
          <thead><tr><th>未成交/流程原因</th><th>次数</th><th>说明</th></tr></thead>
          <tbody>
          {% for item in backtest_result.diagnostics.reasons %}
          <tr><td>{{ item.label }}</td><td>{{ item.count }}</td><td>{{ item.note }}</td></tr>
          {% endfor %}
          </tbody>
        </table>
        {% endif %}
        {% if backtest_result.diagnostics.warnings %}
        <div class="diagnostic-warnings">
          {% for warning in backtest_result.diagnostics.warnings %}<div>⚠ {{ warning }}</div>{% endfor %}
        </div>
        {% endif %}
      </div>
      {% endif %}

      <div class="panel result-card config-summary-card">
        <div class="section-title">当前工作配置{% if config_saved_at %}<span class="compact-note">最后保存：{{ config_saved_at }}</span>{% endif %}</div>
        <div class="compact-note">页面显示的是当前表单；下方“本次回测使用配置”来自提交时的实际选择。</div>
        {% for group in config_summary %}
        <div class="config-summary-row">
          <span>{{ group.category }}（{{ group.count }}项）</span>
          <span>{{ group.labels|join('、') if group.labels else '未选择' }}</span>
        </div>
        {% endfor %}
      </div>
      {% if last_run_summary %}
      <div class="panel result-card config-summary-card locked-config">
        <div class="section-title">最近一次回测实际使用配置（已锁定）{% if last_run_saved_at %}<span class="compact-note">{{ last_run_saved_at }} · {{ last_run_mode }}</span>{% endif %}</div>
        <div class="compact-note">这里不会随页面默认值变化，显示的是上一次点击回测按钮时真正提交的因子和参数。</div>
        {% for group in last_run_summary %}
        <div class="config-summary-row"><span>{{ group.category }}（{{ group.count }}项）</span><span>{{ group.labels|join('、') if group.labels else '未选择' }}</span></div>
        {% endfor %}
      </div>
      {% endif %}

      <div class="panel report-shell">
        <iframe
          id="viewer-report"
          class="viewer-frame {% if active_view != 'report' %}hidden{% endif %}"
          src="{{ report_url or '' }}"
          title="最新回测报告"></iframe>
        <iframe
          id="viewer-multi"
          class="viewer-frame {% if active_view != 'multi' %}hidden{% endif %}"
          src="{{ multi_stock_url }}"
          title="多股票回放"></iframe>
        <iframe
          id="viewer-stock"
          class="viewer-frame {% if active_view != 'stock' %}hidden{% endif %}"
          src="{{ current_stock_url }}"
          title="当前单票回放"></iframe>
        <div id="viewer-interactive" class="viewer-empty {% if active_view != 'interactive' %}hidden{% endif %}">
          左侧就是参数回测台。改完参数直接点“保存临时配置并运行回测”，运行完成后再点上方“最新报告”或“当前单票回放”查看结果。
        </div>
      </div>
    </div>
  </div>
  <script>
    const viewSources = {
      report: {{ (report_url or '')|tojson }},
      multi: {{ multi_stock_url|tojson }},
      stock: {{ current_stock_url|tojson }}
    };
    const buttons = [...document.querySelectorAll('.tab-btn')];
    const views = {
      interactive: document.getElementById('viewer-interactive'),
      report: document.getElementById('viewer-report'),
      multi: document.getElementById('viewer-multi'),
      stock: document.getElementById('viewer-stock')
    };
    function showView(name) {
      buttons.forEach(btn => btn.classList.toggle('active', btn.dataset.view === name));
      Object.entries(views).forEach(([key, node]) => {
        if (!node) return;
        node.classList.toggle('hidden', key !== name);
      });
      if ((name === 'report' || name === 'multi' || name === 'stock') && views[name] && viewSources[name]) {
        if (!views[name].getAttribute('src')) views[name].setAttribute('src', viewSources[name]);
      }
      if (name === 'report' && !viewSources.report) {
        views.interactive.classList.remove('hidden');
        views.report.classList.add('hidden');
        buttons.forEach(btn => btn.classList.toggle('active', btn.dataset.view === 'interactive'));
      }
    }
    buttons.forEach(btn => btn.addEventListener('click', () => showView(btn.dataset.view)));

    const modeTabs = [...document.querySelectorAll('[data-mode-tab]')];
    const modeSections = [...document.querySelectorAll('[data-mode-section]')];
    const uiMode = document.getElementById('uiMode');
    const preset = document.getElementById('strategyPreset');
    const effectiveConfig = document.getElementById('effectiveConfig');
    function field(name) { return document.querySelector(`[name="${name}"]`); }
    function setField(name, value) { const node = field(name); if (node) node.value = value; }
    function valueOf(name, fallback = '') { const node = field(name); return node ? node.value : fallback; }
    function checked(name) { const node = field(name); return Boolean(node && node.checked); }
    function updateSingleEffectiveConfig() {
      const timing = {
        precomputed_stop_entry: '严格预挂单',
        close_confirm_next_open: '收盘确认后次根开盘',
        tb_replay: 'TB复刻',
        same_bar_entry: '本根形成后立即买入',
      }[valueOf('single_entry_timing')] || valueOf('single_entry_timing');
      const grid = checked('single_switch_扩展因子_grid_addon')
        ? `网格加仓 ${valueOf('single_grid_mode')} · 首笔${valueOf('single_grid_initial_ratio')} · 倍数${valueOf('single_grid_multiplier')}`
        : '网格加仓关闭';
      effectiveConfig.innerHTML = `<b>单股当前生效设置：</b>资金 ${valueOf('single_capital')} · 基础仓位 ${valueOf('single_base_position')} · ${timing} · 买入溢价 ${valueOf('single_buy_premium')} · ${grid}`;
    }
    function updateGridFields(prefix) {
      const modeNode = field(`${prefix}_grid_mode`);
      if (!modeNode) return;
      const mode = modeNode.value;
      const fixed = field(`${prefix}_grid_followup_ratio`);
      const multiplier = field(`${prefix}_grid_multiplier`);
      if (fixed) fixed.closest('div').hidden = mode !== 'fixed_tranche';
      if (multiplier) multiplier.closest('div').hidden = mode !== 'multiplier';
      const initial = field(`${prefix}_grid_initial_ratio`);
      if (initial) {
        const holder = initial.closest('div');
        let note = holder.querySelector('.grid-formula-note');
        if (!note) {
          note = document.createElement('p');
          note.className = 'compact-note grid-formula-note';
          holder.appendChild(note);
        }
        note.textContent = mode === 'multiplier'
          ? '先按此比例换算首笔股数，之后按首笔股数的1、2、4、8倍加仓。'
          : mode === 'linear'
            ? '先按此比例换算首笔股数，之后按首笔股数的1、2、3、4倍加仓。'
            : '先按此比例换算首笔股数，之后每层使用相同股数。';
      }
    }
    ['single', 'multi'].forEach(prefix => {
      const node = field(`${prefix}_grid_mode`);
      if (node) {
        node.addEventListener('change', () => updateGridFields(prefix));
        updateGridFields(prefix);
      }
    });
    function showMode(mode) {
      uiMode.value = mode;
      modeTabs.forEach(tab => tab.classList.toggle('active', tab.dataset.modeTab === mode));
      modeSections.forEach(section => section.classList.toggle('mode-hidden', section.dataset.modeSection !== mode));
      if (mode === 'single') updateSingleEffectiveConfig();
    }
    modeTabs.forEach(tab => tab.addEventListener('click', () => showMode(tab.dataset.modeTab)));
    document.querySelectorAll('[name^="single_"]').forEach(node => {
      node.addEventListener('input', updateSingleEffectiveConfig);
      node.addEventListener('change', updateSingleEffectiveConfig);
    });
    function applyPreset(name) {
      if (name === 'standard_grid') {
        showMode('multi');
        setField('multi_portfolio_mode', 'shared_grid');
        setField('multi_capital', 10000000); setField('multi_base_position', 300000);
        setField('multi_max_positions', 30); setField('multi_max_single_ratio', 0.03);
        setField('multi_max_total_ratio', 0.80); setField('multi_cash_floor', 0.20);
        effectiveConfig.innerHTML = '<b>当前方案：</b>标准共享网格 · 1000万组合资金 · 单股上限30万 · 最大持仓30只 · 总仓位80% · 现金底线20%';
      } else if (name === 'conservative_grid') {
        showMode('multi');
        setField('multi_portfolio_mode', 'shared_grid');
        setField('multi_capital', 10000000); setField('multi_base_position', 200000);
        setField('multi_max_positions', 25); setField('multi_max_single_ratio', 0.02);
        setField('multi_max_total_ratio', 0.60); setField('multi_cash_floor', 0.35);
        effectiveConfig.innerHTML = '<b>当前方案：</b>稳健共享网格 · 单股上限20万 · 最大持仓25只 · 总仓位60% · 现金底线35%';
      } else if (name === 'independent_legacy') {
        showMode('multi');
        setField('multi_portfolio_mode', 'independent');
        effectiveConfig.innerHTML = '<b>当前方案：</b>等额独立资金池 · 仅用于旧逻辑结果对照，不执行组合级现金竞争';
      } else {
        effectiveConfig.innerHTML = '<b>当前方案：</b>自定义参数 · 页面不会自动修改你当前的资金和规则设置';
      }
    }
    preset.addEventListener('change', () => applyPreset(preset.value));
    showMode('multi');
  </script>
</body>
</html>
"""


def 读取_yaml(path):
    with open(path, encoding="utf-8") as source:
        return yaml.safe_load(source)


def 写入_yaml(path, data):
    with open(path, "w", encoding="utf-8") as target:
        yaml.safe_dump(data, target, allow_unicode=True, sort_keys=False)


def 读取正式配置():
    return {
        "买入信号配置": 读取_yaml(os.path.join(正式配置目录, "买入信号配置.yaml")),
        "仓位配置": 读取_yaml(os.path.join(正式配置目录, "仓位配置.yaml")),
        "参数配置": 读取_yaml(os.path.join(正式配置目录, "参数配置.yaml")),
        "卖出规则配置": 读取_yaml(os.path.join(正式配置目录, "卖出规则配置.yaml")),
        "模块开关配置": 读取_yaml(os.path.join(正式配置目录, "模块开关配置.yaml")),
        "过滤因子配置": 读取_yaml(os.path.join(正式配置目录, "过滤因子配置.yaml")),
        "因子配置": 读取_yaml(os.path.join(正式配置目录, "因子配置.yaml")),
        "核心模块配置": 读取_yaml(os.path.join(正式配置目录, "核心模块配置.yaml")),
    }


def 读取最近工作台配置():
    """读取最近一次提交的页面配置；它只保存工作台状态，不覆盖正式策略。"""
    if not os.path.isfile(工作台配置路径):
        return {}
    try:
        with open(工作台配置路径, encoding="utf-8") as source:
            payload = json.load(source)
        form = payload.get("form", payload) if isinstance(payload, dict) else {}
        return form if isinstance(form, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def 读取工作台配置时间():
    if not os.path.isfile(工作台配置路径):
        return ""
    try:
        with open(工作台配置路径, encoding="utf-8") as source:
            payload = json.load(source)
        return str(payload.get("更新时间", "")) if isinstance(payload, dict) else ""
    except (OSError, ValueError, json.JSONDecodeError):
        return ""


def 保存最近工作台配置(form):
    """保存页面最后一次提交的表单，供刷新和服务重启后恢复。"""
    if not isinstance(form, dict):
        return False
    os.makedirs(实验记录目录, exist_ok=True)
    payload = {
        "更新时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "form": form,
    }
    temporary_path = f"{工作台配置路径}.tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as target:
            json.dump(payload, target, ensure_ascii=False, indent=2, default=str)
        os.replace(temporary_path, 工作台配置路径)
        return True
    except OSError:
        try:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
        except OSError:
            pass
        return False


def 保存最近回测配置(form, mode="single"):
    """锁定本次真正提交回测的完整页面配置，避免结果与当前表单混淆。"""
    if not isinstance(form, dict):
        return
    os.makedirs(实验记录目录, exist_ok=True)
    payload = {
        "更新时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "模式": mode,
        "form": copy.deepcopy(form),
    }
    temporary_path = f"{最近回测配置路径}.tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as target:
            json.dump(payload, target, ensure_ascii=False, indent=2, default=str)
        os.replace(temporary_path, 最近回测配置路径)
    except OSError:
        try:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
        except OSError:
            pass


def 读取最近回测配置():
    if not os.path.isfile(最近回测配置路径):
        return {}
    try:
        with open(最近回测配置路径, encoding="utf-8") as source:
            payload = json.load(source)
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def 构建工作台表单():
    """正式默认值作为底稿，最近工作配置只覆盖页面字段。"""
    defaults = 构建默认表单()
    saved = 读取最近工作台配置()
    for key, value in saved.items():
        if key in defaults:
            defaults[key] = value
    return defaults


def 工作台配置摘要(form, prefix):
    """列出本次页面实际选择的模块，避免只看数量仍不知道选了什么。"""
    summary = []
    mode_label = "单股" if prefix == "single" else "多股"
    for category, items in 模块显示顺序.items():
        selected = [
            label for module_id, label in items
            if bool(form.get(f"{prefix}_switch_{category}_{module_id}"))
        ]
        summary.append({
            "category": f"{mode_label}·{category}",
            "count": len(selected),
            "labels": selected,
        })
    return summary


模块元信息键 = {"名称", "英文标识", "启用", "状态", "模块", "说明"}


def _按标识取列表项(items, module_id):
    return next((item for item in items if item.get("英文标识") == module_id), {})


def _扩展因子配置键(module_id):
    return "波动率分类器" if module_id == "volatility_classifier" else module_id


def 模块参数字典(config, category, module_id):
    if category == "买入规则":
        item = _按标识取列表项(config["买入信号配置"].get("买入信号列表", []), module_id)
        return {k: v for k, v in item.items() if k not in 模块元信息键}
    if category == "卖出规则":
        item = _按标识取列表项(config["卖出规则配置"].get("卖出条件列表", []), module_id)
        return {k: v for k, v in item.items() if k not in 模块元信息键}
    if category == "过滤因子":
        item = _按标识取列表项(config["过滤因子配置"].get("过滤因子列表", []), module_id)
        return {k: v for k, v in item.items() if k not in 模块元信息键}
    if category == "扩展因子":
        item = config["因子配置"].get("因子列表", {}).get(_扩展因子配置键(module_id), {})
        return copy.deepcopy(item.get("参数", {}) or {})
    return {}


def 模块参数表单键(prefix, category, module_id, param_key):
    return f"{prefix}_param_{category}_{module_id}_{param_key}"


def 参数输入类型(value):
    if isinstance(value, bool):
        return {"type": "bool"}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"type": "number", "step": "1"}
    if isinstance(value, float):
        return {"type": "number", "step": "0.001"}
    if isinstance(value, (list, dict)):
        return {"type": "yaml"}
    return {"type": "text"}


def 参数显示值(value):
    if isinstance(value, (list, dict)):
        return yaml.safe_dump(value, allow_unicode=True, sort_keys=False).strip()
    return value


def 解析参数值(raw_value, default):
    if isinstance(default, bool):
        return raw_value == "on"
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(float(raw_value))
        except (TypeError, ValueError):
            return default
    if isinstance(default, float):
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            return default
    if isinstance(default, (list, dict)):
        try:
            parsed = yaml.safe_load(str(raw_value).strip()) if str(raw_value).strip() else copy.deepcopy(default)
        except yaml.YAMLError:
            return copy.deepcopy(default)
        return parsed if isinstance(parsed, type(default)) else copy.deepcopy(default)
    return str(raw_value)


def 构建模块参数默认值(config, prefix):
    values = {}
    for category, items in 模块显示顺序.items():
        for module_id, _label in items:
            for param_key, value in 模块参数字典(config, category, module_id).items():
                values[模块参数表单键(prefix, category, module_id, param_key)] = copy.deepcopy(value)
    return values


def 构建默认表单():
    config = 读取正式配置()
    positions = config["仓位配置"]["基准仓位"]
    params = config["参数配置"]
    exit_rules = config["卖出规则配置"]["卖出条件列表"]
    switches = config["模块开关配置"]["模块类别"]
    core_config = config["核心模块配置"]
    atr_rule = next(item for item in exit_rules if item["英文标识"] == "atr_trailing")
    shared = {
        "capital": positions["初始资金"],
        "base_position": positions["基础单只金额"],
        "max_positions": positions["最大总持仓数"],
        "max_single_ratio": positions["最大单只比例"],
        "max_total_ratio": positions["最大总仓位比例"],
        "cash_floor": positions["现金底线"],
        "liquidity_limit": 0.01,
        "rsi_period": params["技术指标参数"]["RSI周期"],
        "rsi_price_source": params["技术指标参数"].get("RSI价格源", "close"),
        "entry_timing": params["买入参数"].get("买入时机模式", "precomputed_stop_entry"),
        "rsi_ma_period": params["技术指标参数"]["RSI均线周期"],
        "atr_period": params["技术指标参数"]["ATR周期"],
        "buy_premium": params["交易成本"]["买入溢价"],
        "slippage": params["交易成本"]["滑点"],
        "commission": params["交易成本"]["佣金"],
        "stamp_tax": params["交易成本"].get("印花税", 0.001),
        "transfer_fee": params["交易成本"].get("过户费", 0.00001),
        "signal_expiry_bars": params["技术指标参数"].get("信号过期K线数", 72),
        "atr_exit_multiple": atr_rule["ATR倍数"],
        "hard_stop_multiple": params["卖出参数"]["硬止损倍数"],
        "take_profit_1": params["卖出参数"].get("分批止盈第一档", 0.05),
        "take_profit_2": params["卖出参数"].get("分批止盈第二档", 0.10),
        "take_profit_3": params["卖出参数"].get("分批止盈第三档", 0.20),
        "guard_atr_buffer": params["卖出参数"].get("站岗价ATR缓冲", 0.5),
        "momentum_decline": params["卖出参数"].get("动能衰竭基础阈值", 25),
        "time_exit_bars": params["卖出参数"]["时间退出K线数"],
        "time_exit_loss": params["卖出参数"]["时间退出亏损线"],
        "core_version": core_config.get("版本", "core-v1"),
        "grid_mode": "multiplier",
        "grid_initial_ratio": 0.25,
        "grid_followup_ratio": 0.25,
        "grid_multiplier": 2.0,
    }
    for category, items in 模块显示顺序.items():
        for module_id, _label in items:
            if category == "核心模块" and module_id == "next_bar_entry":
                enabled = core_config.get("核心模块", {}).get("下一根执行", {}).get("启用", True)
            else:
                enabled = switches.get(category, {}).get(module_id, {}).get("启用", False)
            shared[f"switch_{category}_{module_id}"] = bool(enabled)
    form = {
        "single_stock": "600519",
        "single_start": "2020-01-01",
        "single_end": "2023-12-31",
        "single_full_position_mode": True,
        "single_capital": 20000000,
        "single_base_position": 20000000,
        "single_max_positions": 1,
        "single_max_single_ratio": 1.0,
        "single_max_total_ratio": 1.0,
        "single_cash_floor": 0.0,
        "multi_stocks": "",
        "multi_portfolio_mode": "shared_grid",
        "multi_start": "2020-01-01",
        "multi_end": "2023-12-31",
        "multi_workers": 4,
    }
    for prefix in ("single", "multi"):
        for key, value in shared.items():
            form[f"{prefix}_{key}"] = value
        form.update(构建模块参数默认值(config, prefix))
    # Multi-stock defaults use a conservative shared portfolio budget.
    form.update({
        "multi_capital": 10_000_000,
        "multi_base_position": 300_000,
        "multi_max_positions": 30,
        "multi_max_single_ratio": 0.03,
        "multi_max_total_ratio": 0.80,
        "multi_cash_floor": 0.20,
    })
    return form


def 模块字段(form, prefix, category):
    switches = 读取正式配置()["模块开关配置"]["模块类别"]
    config = 读取正式配置()
    result = []
    for module_id, label in 模块显示顺序[category]:
        item = switches.get(category, {}).get(module_id, {})
        status = item.get("状态", "完成") if module_id != "next_bar_entry" else "完成"
        params = []
        for param_key, default_value in 模块参数字典(config, category, module_id).items():
            field = 参数输入类型(default_value)
            form_key = 模块参数表单键(prefix, category, module_id, param_key)
            params.append({
                "key": param_key,
                "name": form_key,
                "value": 参数显示值(form.get(form_key, default_value)),
                "checked": bool(form.get(form_key, default_value)),
                "type": field["type"],
                "step": field.get("step", "1"),
            })
        result.append({
            "name": f"{prefix}_switch_{category}_{module_id}", "label": label,
            "enabled": bool(form.get(f"{prefix}_switch_{category}_{module_id}")),
            "status": status, "disabled": status == "未就绪",
            "params": params,
            "param_note": (
                "打开后：用上一根收盘时的 RSI 状态预先反推本根哨兵价，本根最高价突破后成交。"
                if category == "核心模块" and module_id == "same_bar_entry" else
                "打开后：上一根收盘预计算哨兵价，本根只用最高价突破判断并成交。"
                if category == "核心模块" and module_id == "next_bar_entry" else
                "仅开关控制，无独立可调参数。"
                if category == "核心模块" else
                "当前模块暂无可调参数，保留为占位或由模型文件控制。"
            ),
        })
    return result


def 模块分组字段(form, prefix):
    titles = {
        "买入规则": "② 买入信号规则",
        "卖出规则": "⑤ 卖出与退出风控",
        "过滤因子": "④ 买入前过滤因子",
        "扩展因子": "⑥ 实验扩展因子",
        "核心模块": "③ 成交执行与核心模块",
    }
    return [
        {
            "category": category,
            "title": titles.get(category, category),
            "modules": modules,
            "selected_count": sum(1 for item in modules if item["enabled"]),
        }
        for category in 模块显示顺序
        for modules in [模块字段(form, prefix, category)]
    ]


def 安全读取表单值(form_data, key, caster, default):
    value = form_data.get(key, default)
    try:
        return caster(value)
    except (TypeError, ValueError):
        return default


def 买入时机名称(value):
    return {
        "precomputed_stop_entry": "严格预挂单（无前视）",
        "same_bar_entry": "本根形成哨兵价后立即买入（无前视）",
        "close_confirm_next_open": "收盘确认后次根开盘",
        "tb_replay": "TB复刻模式（最高价RSI同根对照）",
        "legacy_same_bar_lookahead": "本根形成哨兵价后立即买入（无前视）",
        "intrabar_breakout": "本根形成哨兵价后立即买入（无前视）",
    }.get(value, str(value))


def 规范化表单(form_data):
    defaults = 构建默认表单()
    if form_data.get("reset") == "1":
        return defaults
    normalized = copy.deepcopy(defaults)
    text_keys = [
        "single_stock", "single_start", "single_end",
        "multi_stocks", "multi_start", "multi_end",
        "single_rsi_price_source", "multi_rsi_price_source",
        "single_entry_timing", "multi_entry_timing",
        "multi_portfolio_mode",
        "single_grid_mode", "multi_grid_mode",
    ]
    for key in text_keys:
        normalized[key] = str(form_data.get(key, defaults[key])).strip() or defaults[key]
    for prefix in ("single", "multi"):
        if normalized[f"{prefix}_rsi_price_source"] not in ("high", "close", "low"):
            normalized[f"{prefix}_rsi_price_source"] = defaults[f"{prefix}_rsi_price_source"]
        if normalized[f"{prefix}_entry_timing"] not in (
            "precomputed_stop_entry", "close_confirm_next_open",
            "tb_replay", "same_bar_entry", "legacy_same_bar_lookahead", "intrabar_breakout",
        ):
            normalized[f"{prefix}_entry_timing"] = defaults[f"{prefix}_entry_timing"]
        if normalized[f"{prefix}_grid_mode"] not in ("fixed_tranche", "linear", "multiplier"):
            normalized[f"{prefix}_grid_mode"] = defaults[f"{prefix}_grid_mode"]
        if normalized[f"{prefix}_entry_timing"] == "precomputed_stop_entry":
            normalized[f"{prefix}_switch_核心模块_same_bar_entry"] = True
            normalized[f"{prefix}_switch_核心模块_next_bar_entry"] = True
        elif normalized[f"{prefix}_entry_timing"] == "same_bar_entry":
            normalized[f"{prefix}_switch_核心模块_same_bar_entry"] = True
            normalized[f"{prefix}_switch_核心模块_next_bar_entry"] = False
    normalized["single_full_position_mode"] = form_data.get("single_full_position_mode") == "on"
    numeric_fields = {
        "single_capital": float, "single_base_position": float, "single_max_positions": int,
        "single_max_single_ratio": float, "single_max_total_ratio": float, "single_cash_floor": float,
        "single_liquidity_limit": float, "single_rsi_period": int, "single_rsi_ma_period": int,
        "single_atr_period": int, "single_buy_premium": float, "single_slippage": float,
        "single_commission": float, "single_atr_exit_multiple": float, "single_hard_stop_multiple": float,
        "single_stamp_tax": float, "single_transfer_fee": float, "single_signal_expiry_bars": int,
        "single_take_profit_1": float, "single_take_profit_2": float, "single_take_profit_3": float,
        "single_guard_atr_buffer": float, "single_momentum_decline": float,
        "single_time_exit_bars": int, "single_time_exit_loss": float,
        "multi_capital": float, "multi_workers": int, "multi_base_position": float, "multi_max_positions": int,
        "multi_max_single_ratio": float, "multi_max_total_ratio": float, "multi_cash_floor": float,
        "multi_liquidity_limit": float, "multi_rsi_period": int, "multi_rsi_ma_period": int,
        "multi_atr_period": int, "multi_buy_premium": float, "multi_slippage": float,
        "multi_commission": float, "multi_atr_exit_multiple": float, "multi_hard_stop_multiple": float,
        "multi_stamp_tax": float, "multi_transfer_fee": float, "multi_signal_expiry_bars": int,
        "multi_take_profit_1": float, "multi_take_profit_2": float, "multi_take_profit_3": float,
        "multi_guard_atr_buffer": float, "multi_momentum_decline": float,
        "multi_time_exit_bars": int, "multi_time_exit_loss": float,
        "single_grid_initial_ratio": float, "single_grid_followup_ratio": float,
        "single_grid_multiplier": float, "multi_grid_initial_ratio": float,
        "multi_grid_followup_ratio": float, "multi_grid_multiplier": float,
    }
    for key, caster in numeric_fields.items():
        normalized[key] = 安全读取表单值(form_data, key, caster, defaults[key])
    for key in defaults:
        if "_switch_" in key:
            normalized[key] = (
                form_data.get(key) == "on" or form_data.get(key) is True
                if key in form_data else False
            )
        if "_param_" in key:
            normalized[key] = 解析参数值(form_data.get(key), defaults[key])
    # Apply timing invariants after reading checkbox fields; otherwise a stale
    # browser form can override the safe strict-mode defaults above.
    for prefix in ("single", "multi"):
        if normalized[f"{prefix}_entry_timing"] == "precomputed_stop_entry":
            normalized[f"{prefix}_switch_核心模块_same_bar_entry"] = False
            normalized[f"{prefix}_switch_核心模块_next_bar_entry"] = True
        elif normalized[f"{prefix}_entry_timing"] == "same_bar_entry":
            normalized[f"{prefix}_switch_核心模块_same_bar_entry"] = True
            normalized[f"{prefix}_switch_核心模块_next_bar_entry"] = False
    return normalized


def 创建运行目录(stock):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_dir = os.path.join(实验记录目录, f"交互回测_{timestamp}_{stock}")
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


def 清理旧交互回测数据():
    """清理旧的交互回测结果，不触碰行情、配置和数据备份。"""
    if not os.path.isdir(实验记录目录):
        return {"目录数": 0, "字节数": 0}
    root = os.path.realpath(实验记录目录)
    removed = 0
    bytes_removed = 0
    for entry in os.scandir(root):
        if not entry.name.startswith("交互回测_") or not entry.is_dir(follow_symlinks=False):
            continue
        target = os.path.realpath(entry.path)
        if os.path.dirname(target) != root:
            continue
        for current_root, _, filenames in os.walk(target):
            for filename in filenames:
                try:
                    bytes_removed += os.path.getsize(os.path.join(current_root, filename))
                except OSError:
                    pass
        shutil.rmtree(target)
        removed += 1
    最近报告.update({"token": None, "path": None, "run_dir": None})
    最近多股报告.update({"token": None, "path": None, "run_dir": None})
    return {"目录数": removed, "字节数": bytes_removed}


def 恢复最近单票报告():
    """服务重启后恢复最近一次有效单股回测，确保主页面与回放使用同一快照。"""
    if not os.path.isdir(实验记录目录):
        return None
    candidates = []
    for name in os.listdir(实验记录目录):
        if not name.startswith("交互回测_") or name.endswith("_multi"):
            continue
        run_dir = os.path.join(实验记录目录, name)
        report_path = os.path.join(run_dir, "交互回测报告.html")
        if os.path.isfile(report_path):
            candidates.append((os.path.getmtime(report_path), run_dir, report_path))
    if not candidates:
        return None
    _, run_dir, report_path = max(candidates)
    最近报告.update({"token": uuid.uuid4().hex, "path": report_path, "run_dir": run_dir})
    return report_path


def 读取单股回测摘要(run_dir):
    """读取最近回测的展示指标；页面重启后也能与同一份回放快照保持一致。"""
    summary_path = os.path.join(run_dir or "", "回测摘要.txt")
    values = {}
    if not os.path.isfile(summary_path):
        return values
    with open(summary_path, encoding="utf-8") as source:
        for line in source:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    return values


def 复制配置(run_dir):
    snapshot_dir = os.path.join(run_dir, "配置快照_交互")
    shutil.copytree(正式配置目录, snapshot_dir, dirs_exist_ok=True)
    return snapshot_dir


def 应用表单到配置(config_dir, form):
    positions_path = os.path.join(config_dir, "仓位配置.yaml")
    parameters_path = os.path.join(config_dir, "参数配置.yaml")
    exits_path = os.path.join(config_dir, "卖出规则配置.yaml")
    switches_path = os.path.join(config_dir, "模块开关配置.yaml")
    filters_path = os.path.join(config_dir, "过滤因子配置.yaml")
    factors_path = os.path.join(config_dir, "因子配置.yaml")
    core_path = os.path.join(config_dir, "核心模块配置.yaml")

    positions = 读取_yaml(positions_path)
    parameters = 读取_yaml(parameters_path)
    exits = 读取_yaml(exits_path)
    switches = 读取_yaml(switches_path)
    filters = 读取_yaml(filters_path)
    factors = 读取_yaml(factors_path)
    core = 读取_yaml(core_path)

    positions["基准仓位"]["初始资金"] = form["capital"]
    positions["基准仓位"]["基础单只金额"] = form["base_position"]
    if (form.get("full_position_mode")
            and form.get("switch_扩展因子_grid_addon")
            and form.get("grid_initial_ratio") is not None):
        positions["基准仓位"]["基础单只金额"] = (
            float(form["base_position"]) * float(form["grid_initial_ratio"])
        )
    positions["基准仓位"]["最大总持仓数"] = form["max_positions"]
    positions["基准仓位"]["最大单只比例"] = form["max_single_ratio"]
    positions["基准仓位"]["最大总仓位比例"] = form["max_total_ratio"]
    positions["基准仓位"]["现金底线"] = form["cash_floor"]

    parameters["技术指标参数"]["RSI周期"] = form["rsi_period"]
    parameters["技术指标参数"]["RSI价格源"] = form["rsi_price_source"]
    parameters["买入参数"]["买入时机模式"] = form["entry_timing"]
    parameters["技术指标参数"]["RSI均线周期"] = form["rsi_ma_period"]
    parameters["技术指标参数"]["ATR周期"] = form["atr_period"]
    parameters["技术指标参数"]["信号过期K线数"] = form["signal_expiry_bars"]
    parameters["交易成本"]["买入溢价"] = form["buy_premium"]
    parameters["交易成本"]["滑点"] = form["slippage"]
    parameters["交易成本"]["佣金"] = form["commission"]
    parameters["交易成本"]["印花税"] = form["stamp_tax"]
    parameters["交易成本"]["过户费"] = form["transfer_fee"]
    parameters["卖出参数"]["硬止损倍数"] = form["hard_stop_multiple"]
    parameters["卖出参数"]["分批止盈第一档"] = form["take_profit_1"]
    parameters["卖出参数"]["分批止盈第二档"] = form["take_profit_2"]
    parameters["卖出参数"]["分批止盈第三档"] = form["take_profit_3"]
    parameters["卖出参数"]["站岗价ATR缓冲"] = form["guard_atr_buffer"]
    parameters["卖出参数"]["动能衰竭基础阈值"] = form["momentum_decline"]
    parameters["卖出参数"]["时间退出K线数"] = form["time_exit_bars"]
    parameters["卖出参数"]["时间退出亏损线"] = form["time_exit_loss"]
    parameters["仓位参数"]["初始资金"] = form["capital"]
    parameters["仓位参数"]["基础单只金额"] = form["base_position"]
    parameters["仓位参数"]["最大单只比例"] = form["max_single_ratio"]
    parameters["仓位参数"]["最大持仓数"] = form["max_positions"]
    parameters["仓位参数"]["最大总仓位"] = form["max_total_ratio"]
    parameters["仓位参数"]["现金底线"] = form["cash_floor"]

    for item in exits["卖出条件列表"]:
        if item["英文标识"] == "atr_trailing":
            item["ATR倍数"] = form["atr_exit_multiple"]
        if item["英文标识"] == "time_exit":
            item["最大持仓K线数"] = form["time_exit_bars"]
            item["亏损触发"] = form["time_exit_loss"]
        if item["英文标识"] == "take_profit":
            item["第一目标"] = form["take_profit_1"]
            item["第二目标"] = form["take_profit_2"]
            item["第三目标"] = form["take_profit_3"]
        if item["英文标识"] == "stop_loss":
            item["止损倍数"] = form["hard_stop_multiple"]
        if item["英文标识"] == "rsi_guard":
            item["ATR缓冲倍数"] = form["guard_atr_buffer"]
        if item["英文标识"] == "momentum_exit":
            item["基础回落阈值"] = form["momentum_decline"]

    module_params = form.get("module_params", {})
    buy_signals = 读取_yaml(os.path.join(config_dir, "买入信号配置.yaml"))
    for item in buy_signals.get("买入信号列表", []):
        item.update(module_params.get("买入规则", {}).get(item.get("英文标识"), {}))
        module_id = item.get("英文标识")
        item["启用"] = bool(form.get(f"switch_买入规则_{module_id}", item.get("启用", False)))

    for item in exits["卖出条件列表"]:
        item.update(module_params.get("卖出规则", {}).get(item.get("英文标识"), {}))

    for item in filters["过滤因子列表"]:
        item.update(module_params.get("过滤因子", {}).get(item.get("英文标识"), {}))

    for module_id, params in module_params.get("扩展因子", {}).items():
        legacy_id = _扩展因子配置键(module_id)
        if legacy_id in factors["因子列表"]:
            factors["因子列表"][legacy_id]["参数"] = params

    # 网格模式是页面级资金语义，覆盖因子文件中的同名默认值，保证
    # 单股引擎与共享组合层使用同一套选择。
    grid_config = factors["因子列表"].get("grid_addon")
    if isinstance(grid_config, dict):
        grid_params = grid_config.setdefault("参数", {})
        grid_params.update({
            "加仓模式": form.get("grid_mode", "multiplier"),
            "倍数": float(form.get("grid_multiplier", 2.0) or 2.0),
        })

    for item in exits["卖出条件列表"]:
        if item["英文标识"] == "time_exit":
            parameters["卖出参数"]["时间退出K线数"] = item.get("最大持仓K线数", parameters["卖出参数"]["时间退出K线数"])
            parameters["卖出参数"]["时间退出亏损线"] = item.get("亏损触发", parameters["卖出参数"]["时间退出亏损线"])
        if item["英文标识"] == "take_profit":
            parameters["卖出参数"]["分批止盈第一档"] = item.get("第一目标", parameters["卖出参数"]["分批止盈第一档"])
            parameters["卖出参数"]["分批止盈第二档"] = item.get("第二目标", parameters["卖出参数"]["分批止盈第二档"])
            parameters["卖出参数"]["分批止盈第三档"] = item.get("第三目标", parameters["卖出参数"]["分批止盈第三档"])
        if item["英文标识"] == "stop_loss":
            parameters["卖出参数"]["硬止损倍数"] = item.get("止损倍数", parameters["卖出参数"]["硬止损倍数"])
        if item["英文标识"] == "rsi_guard":
            parameters["卖出参数"]["站岗价ATR缓冲"] = item.get("ATR缓冲倍数", parameters["卖出参数"]["站岗价ATR缓冲"])
        if item["英文标识"] == "momentum_exit":
            parameters["卖出参数"]["动能衰竭基础阈值"] = item.get("基础回落阈值", parameters["卖出参数"]["动能衰竭基础阈值"])

    for category, items in 模块显示顺序.items():
        for module_id, _label in items:
            form_key = f"switch_{category}_{module_id}"
            enabled = bool(form[form_key])
            if category == "核心模块" and module_id == "next_bar_entry":
                core["核心模块"]["下一根执行"]["启用"] = enabled
                continue
            switches["模块类别"][category][module_id]["启用"] = enabled
            if category == "卖出规则":
                next(x for x in exits["卖出条件列表"] if x["英文标识"] == module_id)["启用"] = enabled
            elif category == "过滤因子":
                next(x for x in filters["过滤因子列表"] if x["英文标识"] == module_id)["启用"] = enabled
            elif category == "扩展因子":
                legacy_id = "波动率分类器" if module_id == "volatility_classifier" else module_id
                factors["因子列表"][legacy_id]["启用"] = enabled
            elif category == "核心模块":
                core["核心模块"][核心旧名对照[module_id]]["启用"] = enabled
                if module_id == "same_bar_entry":
                    parameters["技术指标参数"]["哨兵价本根形成立即买入"] = enabled

    # Keep execution-mode invariants in the generated snapshot as well as in
    # the form. This protects direct callers and stale browser submissions.
    if form.get("entry_timing") == "precomputed_stop_entry":
        for module_id in ("reverse_price", "sentinel_build", "sentinel_breakout", "sentinel_trailing"):
            switches["模块类别"]["核心模块"][module_id]["启用"] = True
        core["核心模块"]["反推价计算"]["启用"] = True
        core["核心模块"]["哨兵价形成"]["启用"] = True
        core["核心模块"]["哨兵价突破成交"]["启用"] = True
        core["核心模块"]["哨兵价突破后上移"]["启用"] = True
        switches["模块类别"]["核心模块"].setdefault("same_bar_entry", {"名称": "本根形成哨兵价后立即买入", "状态": "完成"})["启用"] = True
        core["核心模块"]["本根形成立即成交"]["启用"] = True
        parameters["技术指标参数"]["哨兵价本根形成立即买入"] = True
        switches["模块类别"]["核心模块"].setdefault("next_bar_entry", {"名称": "下一根执行", "状态": "完成"})["启用"] = True
        core["核心模块"]["下一根执行"]["启用"] = True
    elif form.get("entry_timing") == "same_bar_entry":
        for module_id in ("reverse_price", "sentinel_build", "sentinel_breakout", "sentinel_trailing"):
            switches["模块类别"]["核心模块"][module_id]["启用"] = True
        core["核心模块"]["反推价计算"]["启用"] = True
        core["核心模块"]["哨兵价形成"]["启用"] = True
        core["核心模块"]["哨兵价突破成交"]["启用"] = True
        core["核心模块"]["哨兵价突破后上移"]["启用"] = True
        switches["模块类别"]["核心模块"].setdefault("same_bar_entry", {"名称": "本根形成哨兵价后立即买入", "状态": "完成"})["启用"] = True
        core["核心模块"]["本根形成立即成交"]["启用"] = True
        parameters["技术指标参数"]["哨兵价本根形成立即买入"] = True
        switches["模块类别"]["核心模块"].setdefault("next_bar_entry", {"名称": "下一根执行", "状态": "完成"})["启用"] = False
        core["核心模块"]["下一根执行"]["启用"] = False

    写入_yaml(positions_path, positions)
    写入_yaml(parameters_path, parameters)
    写入_yaml(os.path.join(config_dir, "买入信号配置.yaml"), buy_signals)
    写入_yaml(exits_path, exits)
    写入_yaml(switches_path, switches)
    写入_yaml(filters_path, filters)
    写入_yaml(factors_path, factors)
    写入_yaml(core_path, core)


def 提取模式配置(form, prefix):
    result = {
        "stock": form.get(f"{prefix}_stock", "600519"),
        "stocks": form.get(f"{prefix}_stocks", ""),
        "start": form[f"{prefix}_start"],
        "end": form[f"{prefix}_end"],
        "full_position_mode": form.get(f"{prefix}_full_position_mode", False),
        "portfolio_mode": form.get(f"{prefix}_portfolio_mode", "independent"),
        "workers": form.get(f"{prefix}_workers", 1),
        "capital": form[f"{prefix}_capital"],
        "base_position": form[f"{prefix}_base_position"],
        "max_positions": form[f"{prefix}_max_positions"],
        "max_single_ratio": form[f"{prefix}_max_single_ratio"],
        "max_total_ratio": form[f"{prefix}_max_total_ratio"],
        "cash_floor": form[f"{prefix}_cash_floor"],
        "liquidity_limit": form[f"{prefix}_liquidity_limit"],
        "rsi_period": form[f"{prefix}_rsi_period"],
        "rsi_price_source": form[f"{prefix}_rsi_price_source"],
        "entry_timing": form[f"{prefix}_entry_timing"],
        "rsi_ma_period": form[f"{prefix}_rsi_ma_period"],
        "atr_period": form[f"{prefix}_atr_period"],
        "buy_premium": form[f"{prefix}_buy_premium"],
        "slippage": form[f"{prefix}_slippage"],
        "commission": form[f"{prefix}_commission"],
        "stamp_tax": form[f"{prefix}_stamp_tax"],
        "transfer_fee": form[f"{prefix}_transfer_fee"],
        "signal_expiry_bars": form[f"{prefix}_signal_expiry_bars"],
        "atr_exit_multiple": form[f"{prefix}_atr_exit_multiple"],
        "hard_stop_multiple": form[f"{prefix}_hard_stop_multiple"],
        "take_profit_1": form[f"{prefix}_take_profit_1"],
        "take_profit_2": form[f"{prefix}_take_profit_2"],
        "take_profit_3": form[f"{prefix}_take_profit_3"],
        "guard_atr_buffer": form[f"{prefix}_guard_atr_buffer"],
        "momentum_decline": form[f"{prefix}_momentum_decline"],
        "time_exit_bars": form[f"{prefix}_time_exit_bars"],
        "time_exit_loss": form[f"{prefix}_time_exit_loss"],
        "grid_mode": form[f"{prefix}_grid_mode"],
        "grid_initial_ratio": form[f"{prefix}_grid_initial_ratio"],
        "grid_followup_ratio": form[f"{prefix}_grid_followup_ratio"],
        "grid_multiplier": form[f"{prefix}_grid_multiplier"],
        "grid_max_add_count": int(form.get(
            f"{prefix}_param_扩展因子_grid_addon_最大加仓次数", 5
        ) or 5),
    }
    for category, items in 模块显示顺序.items():
        for module_id, _label in items:
            result[f"switch_{category}_{module_id}"] = form[f"{prefix}_switch_{category}_{module_id}"]
    config = 读取正式配置()
    result["module_params"] = {}
    for category, items in 模块显示顺序.items():
        result["module_params"][category] = {}
        for module_id, _label in items:
            params = {}
            for param_key in 模块参数字典(config, category, module_id):
                params[param_key] = form[模块参数表单键(prefix, category, module_id, param_key)]
            result["module_params"][category][module_id] = params
    return result


def 格式化百分比(value):
    return f"{float(value):+.2f}%"


def 格式化金额(value):
    return f"{float(value):,.0f}"


def 归一化单股满仓参数(form):
    """单股模式下自动切成更适合和个股基准对比的满仓参数。"""
    form = copy.deepcopy(form)
    if form.get("full_position_mode"):
        capital = float(form.get("capital", 0) or 0)
        form["base_position"] = capital
        form["max_positions"] = 1
        form["max_single_ratio"] = 1.0
        form["max_total_ratio"] = 1.0
        form["cash_floor"] = 0.0
    return form


def 应用TB复刻参数(form, prefix="single"):
    form = copy.deepcopy(form)
    form[f"{prefix}_rsi_price_source"] = "high"
    form[f"{prefix}_entry_timing"] = "tb_replay"
    form[f"{prefix}_full_position_mode"] = True if prefix == "single" else form.get(f"{prefix}_full_position_mode", False)
    for module_id, _label in 模块显示顺序["买入规则"]:
        form[f"{prefix}_switch_买入规则_{module_id}"] = True
    for module_id, _label in 模块显示顺序["卖出规则"]:
        form[f"{prefix}_switch_卖出规则_{module_id}"] = (module_id == "tb_rsi_low_exit")
    for category in ("过滤因子", "扩展因子"):
        for module_id, _label in 模块显示顺序[category]:
            form[f"{prefix}_switch_{category}_{module_id}"] = False
    form[f"{prefix}_switch_核心模块_reverse_price"] = True
    form[f"{prefix}_switch_核心模块_sentinel_build"] = True
    form[f"{prefix}_switch_核心模块_sentinel_breakout"] = True
    form[f"{prefix}_switch_核心模块_sentinel_trailing"] = True
    form[f"{prefix}_switch_核心模块_same_bar_entry"] = False
    form[f"{prefix}_switch_核心模块_next_bar_entry"] = True
    return form


def 预检查无成交风险(form, mode):
    issues = []
    if mode == "single":
        prefix = "single"
    else:
        prefix = "multi"

    capital = float(form.get(f"{prefix}_capital", 0) or 0)
    max_single_ratio = float(form.get(f"{prefix}_max_single_ratio", 0) or 0)
    cash_floor = float(form.get(f"{prefix}_cash_floor", 0) or 0)
    base_position = float(form.get(f"{prefix}_base_position", 0) or 0)
    start = str(form.get(f"{prefix}_start", "")).strip()
    end = str(form.get(f"{prefix}_end", "")).strip()
    full_position_mode = bool(form.get(f"{prefix}_full_position_mode"))

    buy_switches = [
        bool(form.get(f"{prefix}_switch_买入规则_rsi_cross_20")),
        bool(form.get(f"{prefix}_switch_买入规则_rsi_cross_30")),
        bool(form.get(f"{prefix}_switch_买入规则_rsi_cross_ma")),
        bool(form.get(f"{prefix}_switch_买入规则_rsi_cross_70")),
    ]

    if start and end and start > end:
        issues.append("开始日期不能晚于结束日期。")
    if capital <= 0:
        issues.append("初始资金必须大于 0。")
    if base_position <= 0:
        issues.append("基础单只金额必须大于 0。")
    if not full_position_mode and cash_floor >= 1:
        issues.append("现金底线不能大于等于 1，否则无法开仓。")
    if max_single_ratio <= 0:
        issues.append("最大单只比例必须大于 0，否则无法开仓。")
    if not full_position_mode and capital > 0 and max_single_ratio > 0 and capital * max_single_ratio < 10000:
        issues.append("最大单只比例过低，按当前资金计算单笔可用金额不足 1 万，极易无成交。")
    if not full_position_mode and capital > 0 and cash_floor < 1 and capital * (1 - cash_floor) < 10000:
        issues.append("现金底线过高，剩余可用开仓资金不足 1 万，极易无成交。")
    if not full_position_mode and base_position < 10000:
        issues.append("基础单只金额低于 1 万，容易因为 100 股起买约束导致无成交。")
    if not any(buy_switches):
        issues.append("买入规则已全部关闭，单股回测不会产生任何成交。")
    if mode == "single" and not str(form.get("single_stock", "")).strip():
        issues.append("单股模式必须填写股票代码。")
    if mode == "multi" and int(form.get("multi_workers", 1) or 1) < 1:
        issues.append("多股并行进程数至少为 1。")
    if mode == "multi" and form.get("multi_portfolio_mode") == "shared_grid":
        total_ratio = float(form.get("multi_max_total_ratio", 0) or 0)
        single_ratio = float(form.get("multi_max_single_ratio", 0) or 0)
        base = float(form.get("multi_base_position", 0) or 0)
        if total_ratio <= 0 or total_ratio > 1:
            issues.append("共享资金池的最大总仓位必须在 0 到 1 之间。")
        if single_ratio <= 0 or single_ratio > 1:
            issues.append("共享资金池的最大单只比例必须在 0 到 1 之间。")
        if base > capital * single_ratio:
            issues.append("共享模式下，单股最大资金上限高于组合资金×最大单只比例；实际会被比例限制，请统一两项设置。")
        if base < 10000:
            issues.append("共享模式下单股最大资金上限低于 1 万元，容易无法买入一手。")
    if str(form.get(f"{prefix}_entry_timing")) == "precomputed_stop_entry":
        if not form.get(f"{prefix}_switch_核心模块_next_bar_entry"):
            issues.append("严格预挂单模式必须启用“下一根执行”，否则不会执行任何买入检查。")
    if str(form.get(f"{prefix}_entry_timing")) == "same_bar_entry":
        if form.get(f"{prefix}_switch_核心模块_next_bar_entry"):
            issues.append("本根形成哨兵价后立即买入模式不能同时启用“下一根执行”。")
        if not form.get(f"{prefix}_switch_核心模块_same_bar_entry"):
            issues.append("本根形成哨兵价后立即买入模式必须启用同名核心模块。")
    return issues


def 构建成交诊断(result, form=None, prefix="single"):
    """从逐根持仓过程生成可读的成交漏斗和未成交原因。"""
    过程 = result.get("持仓过程") if isinstance(result, dict) else None
    if 过程 is None:
        return None
    try:
        records = 过程.to_dict("records") if hasattr(过程, "to_dict") else list(过程)
    except Exception:
        records = []
    counts = Counter()
    reason_counts = Counter()
    observed_limits = set()
    signal_count = breakthrough_count = buy_count = sell_count = 0
    grid_trigger = grid_wait = grid_buy = 0

    def parse(value, default):
        if isinstance(value, (dict, list)):
            return value
        if not value:
            return default
        try:
            return json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return default

    def add_reason(label, note):
        reason_counts[label] += 1
        counts[label] = reason_counts[label]

    for row in records:
        row = row if isinstance(row, dict) else {}
        action = str(row.get("最终动作", ""))
        reason = str(row.get("动作原因", ""))
        signals = parse(row.get("买入信号"), [])
        if isinstance(signals, list) and signals:
            signal_count += 1
            details = [s.get("触发明细", {}) for s in signals if isinstance(s, dict)]
            if any(bool(d.get("价格突破")) or bool(d.get("满足")) for d in details):
                breakthrough_count += 1
        if "买入" in action:
            buy_count += 1
        if "卖出" in action:
            sell_count += 1
        if "尚未突破" in reason:
            add_reason("价格未达到哨兵价", "本根最高价没有达到上一根已确认的哨兵价")
        elif "未启用" in reason:
            add_reason("买入规则未启用", "形成的哨兵价对应规则当前没有打开")
        elif "过滤" in reason and ("拦截" in reason or "未通过" in reason):
            add_reason("过滤因子拦截", reason)
        elif "溢价" in reason and ("高于" in reason or "超过" in reason):
            add_reason("买入价格超出当根范围", "成交模型拒绝了低于当根最低价的计划成交价")
        elif "现金" in reason or "可用金额" in reason:
            add_reason("现金/仓位不足", reason)
        elif "一手" in reason or "数量不足" in reason:
            add_reason("单笔上限不足一手", reason)
        elif "买入执行未成交" in reason:
            buy_decision = parse(row.get("决策记录"), {}).get("买入", {})
            rejection = str(buy_decision.get("成交拒绝原因", "")) if isinstance(buy_decision, dict) else ""
            upper = buy_decision.get("单笔买入上限") if isinstance(buy_decision, dict) else None
            try:
                upper_value = float(upper)
            except (TypeError, ValueError):
                upper_value = None
            if upper_value is not None:
                observed_limits.add(upper_value)
            if "溢价" in rejection:
                add_reason("买入价格超出当根范围", rejection)
            elif "一手" in rejection or "数量" in rejection or "上限" in rejection:
                add_reason("单笔上限不足一手", rejection or "买入金额上限无法买入100股")
            elif "现金" in rejection or "仓位" in rejection:
                add_reason("现金/仓位不足", rejection)
            else:
                add_reason("价格已突破但执行未成交", rejection or "请展开回放查看买入执行证据")
        elif not signals and not action and ("没有满足" in reason or "信号" in reason):
            add_reason("没有形成买入信号", "本根没有满足任何启用的RSI买入条件")

        state = parse(row.get("扩展因子状态"), {})
        grid = state.get("grid_addon", {}) if isinstance(state, dict) else {}
        if isinstance(grid, dict):
            text = json.dumps(grid, ensure_ascii=False)
            if grid.get("触发") or "触发" in text:
                grid_trigger += 1
            if "等待" in text:
                grid_wait += 1
            if grid.get("成交") or "加仓成交" in text:
                grid_buy += 1

    ordered = [
        ("价格未达到哨兵价", "等待下一根K线达到哨兵价"),
        ("单笔上限不足一手", "仅在成交拒绝明确指出一手数量不足时显示；配置上限较小不等于必然拒绝"),
        ("买入价格超出当根范围", "检查K线数据和成交价格设置"),
        ("现金/仓位不足", "检查现金底线、最大单只比例和总仓位"),
        ("过滤因子拦截", "关闭过滤因子或查看具体过滤证据"),
        ("买入规则未启用", "打开对应RSI上穿规则"),
        ("价格已突破但执行未成交", "展开回放查看成交拒绝原因"),
        ("没有形成买入信号", "检查RSI价格源、周期和买入规则"),
    ]
    reasons = [
        {"label": label, "count": counts.get(label, 0), "note": note}
        for label, note in ordered if counts.get(label, 0)
    ]
    warnings = []
    if observed_limits and counts.get("单笔上限不足一手", 0):
        limits_text = "、".join(f"{v:,.0f}" for v in sorted(observed_limits))
        warnings.append(f"本次有成交拒绝明确指出一手数量不足；相关单笔买入上限为 {limits_text} 元。请结合触发K线价格确认是否需要提高上限。")
    # 直接提示当前常见配置冲突：每个启用买入规则的单笔上限低于一手金额。
    if isinstance(form, dict):
        base = float(form.get(f"{prefix}_base_position", 0) or 0)
        params = form.get("module_params", {}) or {}
        buy_params = params.get("买入规则", {}) if isinstance(params, dict) else {}
        limits = []
        for module_id, label in 模块显示顺序["买入规则"]:
            if form.get(f"{prefix}_switch_买入规则_{module_id}"):
                p = buy_params.get(module_id, {}) if isinstance(buy_params, dict) else {}
                value = p.get("单笔买入上限") if isinstance(p, dict) else None
                if value is not None:
                    try: limits.append((label, float(value)))
                    except (TypeError, ValueError): pass
        if limits:
            low = min(v for _, v in limits)
            warnings.append(f"启用买入规则中最低单笔买入上限为 {low:,.0f} 元；若当前股票100股金额高于该值，会全部被拒绝。建议不低于基础单只金额或当前股价×100股。")
        if base and base < 10000:
            warnings.append(f"基础单只金额为 {base:,.0f} 元，低于A股最低一手约束。")
    priority = ["单笔上限不足一手", "买入价格超出当根范围", "现金/仓位不足", "过滤因子拦截", "价格已突破但执行未成交", "价格未达到哨兵价", "买入规则未启用", "没有形成买入信号"]
    headline = next((label for label in priority if counts.get(label, 0)), "没有形成买入信号" if signal_count == 0 else "未发现明确拦截原因")
    return {
        "headline": headline,
        "summary": [
            {"label": "买入信号形成", "value": signal_count},
            {"label": "价格突破哨兵价", "value": breakthrough_count},
            {"label": "实际买入成交", "value": buy_count},
            {"label": "实际卖出成交", "value": sell_count},
            {"label": "网格触发", "value": grid_trigger},
            {"label": "网格等待信号", "value": grid_wait},
            {"label": "网格实际加仓", "value": grid_buy},
            {"label": "记录K线数", "value": len(records)},
        ],
        "reasons": reasons,
        "warnings": warnings,
    }


def 初始化结果():
    return {
        "status": "等待你提交一次回测参数",
        "error": False,
        "metrics": {
            "total_return": "--",
            "max_drawdown": "--",
            "win_rate": "--",
            "final_equity": "--",
        },
        "report_url": None,
        "run_dir": None,
        "active_view": "interactive",
        "backtest_result": {
            "mode": "未运行",
            "sample_count": "--",
            "output_name": "--",
            "rows": [],
            "note": "",
            "diagnostics": None,
        },
    }


def 运行交互回测(form):
    form = 归一化单股满仓参数(提取模式配置(form, "single"))
    清理旧交互回测数据()
    stock = form["stock"]
    run_dir = 创建运行目录(stock)
    config_dir = 复制配置(run_dir)
    应用表单到配置(config_dir, form)
    result = 跑回测(
        stock,
        开始日期=form["start"],
        结束日期=form["end"],
        初始资金=form["capital"],
        配置目录=config_dir,
        运行参数={
            "流动性上限比例": form["liquidity_limit"],
            "单股全仓模式": bool(form.get("full_position_mode")),
        },
        静默=True,
    )
    if result is None:
        raise RuntimeError("回测没有生成可用结果，请检查股票代码、日期范围或数据完整性。")
    保存结果(result, 输出目录=run_dir)
    report_path = os.path.join(run_dir, "交互回测报告.html")
    生成报告(result, result.get("原始K线数据"), 输出路径=report_path)
    token = uuid.uuid4().hex
    最近报告.update({"token": token, "path": report_path, "run_dir": run_dir})
    buys = int(result.get("买入次数", 0))
    sells = int(result.get("卖出次数", 0))
    no_trade = buys == 0 and sells == 0
    return {
        "status": (
            f"回测完成但无成交：{stock} · {form['start']} 到 {form['end']}"
            if no_trade else
            f"回测完成：{stock} · {form['start']} 到 {form['end']}"
        ),
        "error": False,
        "metrics": {
            "total_return": 格式化百分比(result.get("总收益率", 0)),
            "max_drawdown": f"{float(result.get('最大回撤', 0)):.2f}%",
            "win_rate": f"{float(result.get('胜率', 0)):.2f}%",
            "final_equity": 格式化金额(result.get("最终权益", 0)),
        },
        "report_url": f"/report/{token}",
        "run_dir": run_dir,
        "active_view": "report",
            "backtest_result": {
            "mode": "单股回测",
            "sample_count": form["stock"],
            "output_name": os.path.basename(run_dir),
            "rows": [
                {"label": "股票代码", "value": form["stock"]},
                {"label": "时间区间", "value": f"{form['start']} ~ {form['end']}"},
                {"label": "RSI价格源", "value": {"high": "最高价", "close": "收盘价", "low": "最低价"}.get(form["rsi_price_source"], form["rsi_price_source"])},
                {"label": "买入时机", "value": 买入时机名称(form["entry_timing"])},
                {"label": "时序审计", "value": result.get("时序审计", {}).get("结论", "--")},
                {"label": "初始资金", "value": 格式化金额(form["capital"])},
                {"label": "总收益率", "value": 格式化百分比(result.get("总收益率", 0))},
                {"label": "最大回撤", "value": f"{float(result.get('最大回撤', 0)):.2f}%"},
                {"label": "胜率", "value": f"{float(result.get('胜率', 0)):.2f}%"},
                {"label": "买入次数", "value": str(buys)},
                {"label": "卖出次数", "value": str(sells)},
            ],
            "note": (
                "这次没有任何成交，所以收益率会显示 0.00%。常见原因是：最大单只比例设得过低，或买入规则被全部关闭。"
                if no_trade else
                "右侧“最新报告”和“当前单票回放”都已经同步更新。"
            ),
            "diagnostics": 构建成交诊断(result, form, "single"),
        },
    }


def 解析多股输入(form):
    if form["stocks"].strip():
        return 读取多股列表(form["stocks"])
    return 读取多股列表(沪深300列表路径)


def 格式化小数百分比(value):
    return f"{float(value) * 100:+.2f}%"


def 构建组合分析曲线(details, stocks, initial_capital, per_stock_capital, start_date=None, end_date=None):
    """将独立资金池逐日汇总为组合权益、现金、持仓市值和HS300基准。"""
    import pandas as pd

    stock_daily = {}
    all_dates = set()
    for item in details:
        if "错误" in item:
            continue
        holding_path = os.path.join(item.get("结果目录", ""), "持仓过程.csv")
        try:
            holding = pd.read_csv(holding_path, encoding="utf-8-sig")
            holding["_日期键"] = holding["日期"].astype(str).str[:10]
            for column in ("当前现金", "持仓市值", "权益"):
                holding[column] = pd.to_numeric(holding[column], errors="coerce")
            daily = holding.dropna(subset=["权益"]).groupby("_日期键", sort=True).tail(1)
            points = {}
            for _, row in daily.iterrows():
                day = str(row["_日期键"])
                points[day] = {
                    "现金": float(row.get("当前现金", per_stock_capital) or 0),
                    "持仓市值": float(row.get("持仓市值", 0) or 0),
                    "权益": float(row.get("权益", per_stock_capital) or per_stock_capital),
                }
                all_dates.add(day)
            if points:
                stock_daily[str(item.get("股票代码", ""))] = points
        except (OSError, ValueError, KeyError, pd.errors.ParserError):
            continue

    hs_path = os.path.join(项目根目录, "数据模块", "大盘数据", "hs300_日K线.pkl")
    hs_map = {}
    if os.path.exists(hs_path):
        try:
            hs_data = pd.read_pickle(hs_path)
            hs_data["date"] = hs_data["date"].astype(str).str[:10]
            hs_map = dict(zip(hs_data["date"], pd.to_numeric(hs_data["close"], errors="coerce")))
        except (OSError, ValueError, KeyError):
            hs_map = {}

    dates = sorted(day for day in all_dates if (not start_date or day >= start_date) and (not end_date or day <= end_date))
    last_values = {
        stock: {"现金": per_stock_capital, "持仓市值": 0.0, "权益": per_stock_capital}
        for stock in stocks
    }
    hs_first = next((float(hs_map[day]) for day in dates if day in hs_map and pd.notna(hs_map[day]) and float(hs_map[day]) > 0), 0.0)
    hs_last = hs_first
    curve = []
    for day in dates:
        for stock in stocks:
            if day in stock_daily.get(stock, {}):
                last_values[stock] = stock_daily[stock][day]
        cash = sum(value["现金"] for value in last_values.values())
        market_value = sum(value["持仓市值"] for value in last_values.values())
        equity = sum(value["权益"] for value in last_values.values())
        if day in hs_map and pd.notna(hs_map[day]) and float(hs_map[day]) > 0:
            hs_last = float(hs_map[day])
        curve.append({
            "日期": day,
            "权益": round(equity, 2),
            "现金": round(cash, 2),
            "持仓市值": round(market_value, 2),
            "资金使用率": round(market_value / max(equity, 1.0), 6),
            "沪深300权益": round(initial_capital * hs_last / hs_first, 2) if hs_first else None,
        })
    return curve


def 生成多股策略回放页面(path, token, run_dir, details, summary, form, equity_curve):
    """生成本次多股回测专属入口，股票页仍使用单股回放模板。"""
    rows = []
    config_lines = []
    first_stock_url = ""
    fallback_stock_url = ""
    for category, items in 模块显示顺序.items():
        selected = [label for module_id, label in items if form.get(f"switch_{category}_{module_id}")]
        config_lines.append(f"<div><b>多股·{category}</b>（{len(selected)}项）：{'、'.join(selected) if selected else '未选择'}</div>")
    config_lines.insert(0, f"<div><b>资金模式</b>：{summary.get('资金模式', '等额独立资金池')}</div>")
    config_lines.insert(1, f"<div><b>网格加仓模式</b>：{ {'fixed_tranche': '固定分层（实验）', 'linear': '线性递增（实验）', 'multiplier': '倍数加仓（实验）'}.get(summary.get('网格加仓模式', form.get('grid_mode', 'multiplier')), '未识别') }</div>")
    audit_by_stock = {}
    legacy_stock_summary = {}
    if summary.get("资金审计"):
        audit = summary["资金审计"]
        config_lines.append(
            "<div><b>资金审计</b>："
            f"买入成交 {audit.get('买入成交', 0)}，网格加仓 {audit.get('网格加仓成交', 0)}，"
            f"资金拦截 {audit.get('资金不足拦截', 0)}，现金拦截 {audit.get('现金不足拦截', 0)}，"
            f"持仓上限拦截 {audit.get('最大持仓拦截', 0)}</div>"
        )
        for row in summary.get("组合成交明细", []):
            stock = str(row.get("股票代码", ""))
            item = audit_by_stock.setdefault(stock, {"成交": 0, "拦截": 0, "使用资金": 0.0})
            legacy = legacy_stock_summary.setdefault(stock, {
                "实际买入": 0, "实际卖出": 0, "组合拦截": 0,
                "期末股数": 0, "买入净额": 0.0, "卖出净额": 0.0, "最后价格": 0.0,
            })
            price = float(row.get("成交价", 0) or 0)
            if price > 0:
                legacy["最后价格"] = price
            if row.get("结果") == "实际成交":
                item["成交"] += 1
                quantity = int(float(row.get("成交股数", 0) or 0))
                net = float(row.get("成交净额", price * quantity) or price * quantity)
                if row.get("类型") == "买入":
                    item["使用资金"] += price * quantity
                    legacy["实际买入"] += 1
                    legacy["期末股数"] += quantity
                    legacy["买入净额"] += net
                elif row.get("类型") == "卖出":
                    legacy["实际卖出"] += 1
                    legacy["期末股数"] = max(0, legacy["期末股数"] - quantity)
                    legacy["卖出净额"] += net
            else:
                item["拦截"] += 1
                legacy["组合拦截"] += 1
    stock_capital = float(form.get("base_position", 0) or 0)
    for legacy in legacy_stock_summary.values():
        contribution = (
            legacy.pop("卖出净额") - legacy.pop("买入净额")
            + legacy["期末股数"] * legacy.pop("最后价格")
        )
        legacy["收益贡献"] = contribution
        legacy["收益贡献率"] = contribution / stock_capital if stock_capital else 0.0
    for item in details:
        stock = str(item.get("股票代码", ""))
        if "错误" in item:
            rows.append(f"<tr><td>{stock}</td><td colspan='4'>失败：{item['错误']}</td></tr>")
            continue
        url = f"/multi/{token}/stock/{stock}"
        if not fallback_stock_url:
            fallback_stock_url = url
        return_pct = float(item.get('总收益率', 0)) * 100
        audit_stock = audit_by_stock.get(stock, {})
        if summary.get('资金模式') == '共享资金池网格':
            portfolio_stock = summary.get("组合股票汇总", {}).get(stock) or legacy_stock_summary.get(stock, {})
            actual_buys = int(portfolio_stock.get("实际买入", 0))
            actual_sells = int(portfolio_stock.get("实际卖出", 0))
            contribution_pct = float(portfolio_stock.get("收益贡献率", 0)) * 100
            if not first_stock_url and actual_buys + actual_sells > 0:
                first_stock_url = url
            rows.append(
                f"<tr data-stock='{stock}' data-return='{contribution_pct}' data-drawdown='{float(item.get('最大回撤', 0))*100}' data-trades='{actual_buys + actual_sells}'>"
                f"<td><a href='{url}' target='stock_view' title='查看组合实际成交回放'>{stock}</a></td>"
                f"<td class='{'positive' if contribution_pct >= 0 else 'negative'}'>{contribution_pct:+.2f}%</td>"
                f"<td>{actual_buys}/{actual_sells}</td>"
                f"<td>{int(portfolio_stock.get('期末股数', 0)):,}</td>"
                f"<td>{int(portfolio_stock.get('组合拦截', audit_stock.get('拦截', 0)))}</td>"
                f"<td class='muted-cell'>{return_pct:+.2f}%</td></tr>"
            )
        else:
            if not first_stock_url:
                first_stock_url = url
            rows.append(
                f"<tr data-stock='{stock}' data-return='{return_pct}' data-drawdown='{float(item.get('最大回撤', 0))*100}'>"
                f"<td><a href='{url}' target='stock_view'>{stock}</a></td>"
                f"<td class='{'positive' if return_pct >= 0 else 'negative'}'>{return_pct:+.2f}%</td>"
                f"<td>{float(item.get('最大回撤', 0))*100:.2f}%</td>"
                f"<td>{int(item.get('买入次数', 0))}/{int(item.get('卖出次数', 0))}</td>"
                f"<td>{float(item.get('最终权益', 0)):,.0f}</td></tr>"
            )
    first_stock_url = first_stock_url or fallback_stock_url
    page = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>多股策略决策回放</title>
<style>:root{{--bg:#090d15;--panel:#111827;--panel2:#172033;--line:#283449;--text:#e8edf6;--muted:#8490a5;--blue:#7184ff;--cyan:#39d6bd;--red:#ff617d;--gold:#f4bd50;--purple:#a774e8;--stock-width:360px}}*{{box-sizing:border-box}}html,body{{height:100%;margin:0;background:#090d15;color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}}button,input{{font:inherit}}body{{display:flex;flex-direction:column;gap:8px;padding:8px;overflow:hidden}}.overview,.chart-card,.panel{{background:#111827;border:1px solid var(--line);border-radius:7px}}.overview{{padding:9px 11px;flex:none}}.overview-head{{display:flex;align-items:center;gap:10px;margin-bottom:7px}}h1{{font-size:17px;color:var(--red);margin:0;white-space:nowrap}}.fund-note{{font-size:10px;color:var(--gold);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}}.config-button{{border:1px solid var(--line);background:#202b40;color:var(--text);border-radius:5px;padding:5px 9px;cursor:pointer;white-space:nowrap}}.metric-grid{{display:grid;grid-template-columns:repeat(6,minmax(110px,1fr));gap:6px}}.metric{{background:#172135;border:1px solid #26334a;border-radius:6px;padding:6px 8px}}.metric span{{display:block;color:var(--muted);font-size:9px;margin-bottom:2px}}.metric b{{font-size:14px;color:#fff}}.metric .good{{color:var(--cyan)}}.config-summary{{display:flex;gap:6px;margin-top:6px;overflow:hidden}}.config-summary div{{background:#151e30;border-radius:4px;padding:4px 7px;color:var(--muted);font-size:9px;white-space:nowrap}}.config-summary b{{color:#cbd5e1}}.analysis{{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(300px,1fr);gap:8px;height:clamp(170px,27vh,320px);min-height:140px;resize:vertical;overflow:hidden;flex:none}}.chart-card{{position:relative;min-width:0;min-height:0;padding:32px 9px 7px}}.chart-title{{position:absolute;left:11px;top:8px;font-size:12px;font-weight:700}}.legend{{position:absolute;right:11px;top:8px;display:flex;gap:10px;font-size:10px;color:var(--muted)}}.legend i{{display:inline-block;width:14px;height:2px;margin-right:4px;vertical-align:middle}}canvas{{width:100%;height:100%;display:block}}.main{{display:grid;grid-template-columns:minmax(270px,var(--stock-width)) 6px minmax(0,1fr);min-height:280px;flex:1;overflow:hidden}}.splitter{{cursor:col-resize;background:#263248;border-radius:3px;margin:5px 1px}}.splitter:hover{{background:var(--blue)}}.stock-panel{{display:flex;flex-direction:column;overflow:hidden}}.stock-tools{{display:flex;gap:6px;padding:8px;border-bottom:1px solid var(--line)}}.stock-tools input{{min-width:0;flex:1;background:#0c1220;border:1px solid var(--line);color:#fff;border-radius:5px;padding:6px 8px;outline:none}}.stock-tools button{{border:1px solid var(--line);background:#1a2437;color:var(--muted);border-radius:5px;padding:5px 7px;cursor:pointer}}.table-wrap{{overflow:auto;min-height:0}}table{{width:100%;border-collapse:collapse;font-size:11px}}thead{{position:sticky;top:0;z-index:2;background:#172033}}th,td{{padding:7px;border-bottom:1px solid #222e42;text-align:right;white-space:nowrap}}th:first-child,td:first-child{{text-align:left}}tbody tr:hover{{background:#19243a}}a{{color:#93a4ff;text-decoration:none}}.positive{{color:var(--red)}}.negative{{color:var(--cyan)}}.muted-cell{{color:var(--muted)}}.viewer{{overflow:hidden}}iframe{{width:100%;height:100%;border:0;background:var(--bg)}}.config-pop{{position:fixed;inset:0;display:none;z-index:20;background:rgba(4,7,12,.7);align-items:flex-start;justify-content:flex-end;padding:58px 20px}}.config-pop.open{{display:flex}}.config-body{{width:min(620px,85vw);max-height:70vh;overflow:auto;background:#151e30;border:1px solid #35425a;border-radius:7px;padding:14px}}.config-body div{{padding:7px 0;border-bottom:1px solid var(--line);font-size:11px;line-height:1.5}}body.analysis-collapsed .analysis{{height:0;min-height:0;visibility:hidden}}@media(max-width:1050px){{.metric-grid{{grid-template-columns:repeat(3,1fr)}}.analysis{{grid-template-columns:1fr;height:240px;overflow:auto}}.main{{grid-template-columns:300px 5px minmax(650px,1fr);overflow:auto}}}}@media(max-height:760px){{.analysis{{height:180px}}.metric{{padding:4px 7px}}}}</style></head>
<body><section class="overview"><div class="overview-head"><h1>多股策略决策回放台</h1><div class="fund-note">{summary.get('资金模式', '等额独立资金池')} · {('单股上限 '+format(float(form.get('base_position', 0)), ',.0f')+' 元，组合统一审批' if form.get('portfolio_mode') == 'shared_grid' else '每股约 '+format(float(form['capital'])/max(len(details),1), ',.0f')+' 元')} · 实际成交才显示箭头和连线</div><button class="config-button" id="analysisToggle">收起图表</button><button class="config-button" id="configToggle">策略配置</button></div><div class="metric-grid"><div class="metric"><span>组合初始资金</span><b>{float(summary.get('组合初始资金', form['capital'])):,.0f}</b></div><div class="metric"><span>组合最终权益</span><b>{float(summary.get('组合最终权益', form['capital'])):,.0f}</b></div><div class="metric"><span>组合收益</span><b class="good">{float(summary.get('组合总收益率', 0))*100:+.2f}%</b></div><div class="metric"><span>组合最大回撤</span><b>{float(summary.get('组合最大回撤', 0))*100:.2f}%</b></div><div class="metric"><span>最大使用资金</span><b>{float(summary.get('最大使用资金', 0)):,.0f}</b></div><div class="metric"><span>最小非零使用资金</span><b>{float(summary.get('最小使用资金', 0)):,.0f}</b></div></div><div class="config-summary">{''.join(config_lines)}</div></section>
<section class="analysis"><div class="chart-card"><div class="chart-title">组合累计收益 vs 沪深300</div><div class="legend"><span><i style="background:#7184ff"></i>组合</span><span><i style="background:#a774e8"></i>沪深300</span><span><i style="background:#39d6bd"></i>超额</span></div><canvas id="returnChart"></canvas></div><div class="chart-card"><div class="chart-title">资金使用与可用现金</div><div class="legend"><span><i style="background:#f4bd50"></i>持仓市值</span><span><i style="background:#39d6bd"></i>现金</span><span><i style="background:#7184ff"></i>使用率</span></div><canvas id="capitalChart"></canvas></div></section>
<main class="main"><section class="panel stock-panel"><div class="stock-tools"><input id="stockSearch" placeholder="搜索股票代码"><button data-sort="trades">成交优先</button><button data-sort="return">贡献排序</button></div><div class="table-wrap"><table id="stockTable"><thead><tr>{'<th>股票</th><th>组合贡献</th><th>实际买/卖</th><th>期末股数</th><th>组合拦截</th><th>候选收益</th>' if summary.get('资金模式') == '共享资金池网格' else '<th>股票</th><th>收益</th><th>回撤</th><th>买/卖</th><th>期末权益</th>'}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></section><div class="splitter" id="mainSplitter" title="拖动调整股票列表宽度"></div><section class="panel viewer"><iframe name="stock_view" src="{first_stock_url}" title="股票策略决策回放"></iframe></section></main>
<div class="config-pop" id="configPop"><div class="config-body"><strong>本次多股策略配置</strong>{''.join(config_lines)}</div></div>
<script>const curve={json.dumps(equity_curve, ensure_ascii=False)};const initial={float(summary.get('组合初始资金', form['capital']))};const money=v=>new Intl.NumberFormat('zh-CN',{{maximumFractionDigits:0}}).format(v);function setupCanvas(id){{const canvas=document.getElementById(id),rect=canvas.getBoundingClientRect(),dpr=window.devicePixelRatio||1;canvas.width=Math.max(1,rect.width*dpr);canvas.height=Math.max(1,rect.height*dpr);const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);return{{canvas,ctx,w:rect.width,h:rect.height}}}}function line(ctx,values,x,y,color,width=2,dash=[]){{ctx.beginPath();ctx.strokeStyle=color;ctx.lineWidth=width;ctx.setLineDash(dash);values.forEach((v,i)=>{{if(v==null)return;const px=x(i),py=y(v);i?ctx.lineTo(px,py):ctx.moveTo(px,py)}});ctx.stroke();ctx.setLineDash([])}}function grid(ctx,w,h,min,max,format){{ctx.font='10px sans-serif';ctx.fillStyle='#7f8ba0';ctx.strokeStyle='#263248';ctx.lineWidth=1;for(let i=0;i<5;i++){{const y=15+i*(h-32)/4,value=max-(max-min)*i/4;ctx.beginPath();ctx.moveTo(48,y);ctx.lineTo(w-8,y);ctx.stroke();ctx.fillText(format(value),4,y+3)}}}}function drawReturns(){{const{{ctx,w,h}}=setupCanvas('returnChart');if(!curve.length)return;const strategy=curve.map(p=>(p.权益/initial-1)*100),hs=curve.map(p=>p['沪深300权益']?(p['沪深300权益']/initial-1)*100:null),alpha=strategy.map((v,i)=>hs[i]==null?null:v-hs[i]);const vals=[...strategy,...hs,...alpha].filter(Number.isFinite),min=Math.min(...vals,0),max=Math.max(...vals,0),span=max-min||1,x=i=>48+i*(w-58)/Math.max(1,curve.length-1),y=v=>15+(max-v)/span*(h-32);grid(ctx,w,h,min,max,v=>v.toFixed(1)+'%');line(ctx,strategy,x,y,'#7184ff',2.4);line(ctx,hs,x,y,'#a774e8',1.8);line(ctx,alpha,x,y,'#39d6bd',1.4,[5,3]);ctx.fillStyle='#7184ff';ctx.fillText('组合 '+strategy.at(-1).toFixed(2)+'%',52,12);if(hs.at(-1)!=null){{ctx.fillStyle='#a774e8';ctx.fillText('沪深300 '+hs.at(-1).toFixed(2)+'%',145,12);ctx.fillStyle='#39d6bd';ctx.fillText('超额 '+alpha.at(-1).toFixed(2)+'%',260,12)}}}}function drawCapital(){{const{{ctx,w,h}}=setupCanvas('capitalChart');if(!curve.length)return;const cash=curve.map(p=>p.现金),used=curve.map(p=>p['持仓市值']),rate=curve.map(p=>p['资金使用率']*100),max=Math.max(initial,...cash,...used),x=i=>48+i*(w-58)/Math.max(1,curve.length-1),y=v=>15+(max-v)/max*(h-32),yr=v=>15+(100-v)/100*(h-32);grid(ctx,w,h,0,max,v=>money(v/10000)+'万');line(ctx,used,x,y,'#f4bd50',2);line(ctx,cash,x,y,'#39d6bd',1.8);line(ctx,rate,x,yr,'#7184ff',1.4,[4,3]);ctx.fillStyle='#7184ff';ctx.fillText('当前使用率 '+rate.at(-1).toFixed(1)+'%',w-125,12)}}function draw(){{drawReturns();drawCapital()}}window.addEventListener('resize',draw);new ResizeObserver(draw).observe(document.querySelector('.analysis'));draw();document.getElementById('analysisToggle').onclick=e=>{{document.body.classList.toggle('analysis-collapsed');e.target.textContent=document.body.classList.contains('analysis-collapsed')?'展开图表':'收起图表';setTimeout(draw,50)}};const pop=document.getElementById('configPop');document.getElementById('configToggle').onclick=()=>pop.classList.add('open');pop.onclick=e=>{{if(e.target===pop)pop.classList.remove('open')}};document.getElementById('stockSearch').oninput=e=>{{const q=e.target.value.trim();document.querySelectorAll('#stockTable tbody tr').forEach(row=>row.hidden=!row.dataset.stock?.includes(q))}};document.querySelectorAll('[data-sort]').forEach(button=>button.onclick=()=>{{const key=button.dataset.sort,tbody=document.querySelector('#stockTable tbody'),rows=[...tbody.rows];rows.sort((a,b)=>Number(b.dataset[key]||0)-Number(a.dataset[key]||0));rows.forEach(row=>tbody.appendChild(row))}});document.querySelectorAll('#stockTable a').forEach(link=>link.onclick=()=>{{document.querySelectorAll('#stockTable tr').forEach(row=>row.style.background='');link.closest('tr').style.background='#202d47'}});const splitter=document.getElementById('mainSplitter');let resizing=false;splitter.onpointerdown=e=>{{resizing=true;splitter.setPointerCapture(e.pointerId)}};splitter.onpointermove=e=>{{if(!resizing)return;const left=document.querySelector('.main').getBoundingClientRect().left,width=Math.max(270,Math.min(620,e.clientX-left));document.documentElement.style.setProperty('--stock-width',width+'px')}};splitter.onpointerup=()=>resizing=false;</script></body></html>'''
    with open(path, "w", encoding="utf-8") as target:
        target.write(page)


def _读取配置快照(config_dir):
    snapshot = {}
    if not config_dir or not os.path.isdir(config_dir):
        return snapshot
    for name in os.listdir(config_dir):
        path = os.path.join(config_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as source:
                snapshot[name] = json.load(source) if name.endswith(".json") else yaml.safe_load(source)
        except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError):
            continue
    return snapshot


def _准备回放K线(raw, holding):
    start = str(holding["日期"].iloc[0])[:10]
    end = str(holding["日期"].iloc[-1])[:10]
    day = raw["日期"].astype(str).str[:10]
    selected = raw[(day >= start) & (day <= end)].copy()
    if "完整时间" in selected.columns:
        timestamps = pd.to_datetime(selected["完整时间"], errors="coerce")
    else:
        timestamps = pd.Series(
            pd.to_datetime(selected.index, errors="coerce"), index=selected.index
        )
    fallback = pd.to_datetime(selected["日期"], errors="coerce")
    selected["完整时间"] = timestamps.where(timestamps.notna(), fallback).dt.strftime("%Y-%m-%d %H:%M")
    return selected.reset_index(drop=True)


def _审计K线索引(audit_rows, raw):
    exact = {}
    by_day = {}
    for index, value in enumerate(raw["完整时间"].astype(str)):
        exact.setdefault(value[:16], []).append(index)
        by_day.setdefault(value[:10], []).append(index)
    used = set()
    located = []
    for audit in audit_rows:
        timestamp = str(audit.get("时间", ""))[:16]
        candidates = exact.get(timestamp, []) or by_day.get(timestamp[:10], [])
        index = next((value for value in candidates if value not in used), candidates[-1] if candidates else None)
        if index is not None and audit.get("结果") == "实际成交":
            used.add(index)
        row = dict(audit)
        row["K线索引"] = index
        located.append(row)
    return located


def _构建组合实际交易(stock, audit_rows, raw):
    columns = [
        "序号", "股票代码", "持仓组ID", "网格级别", "时间", "K线时间", "K线索引",
        "类型", "买入价", "卖出价", "前复权成交价", "前复权买入价", "前复权卖出价",
        "信号类型", "卖出原因", "成交数量", "仓位", "交易费用", "总成本", "卖出净金额",
        "盈亏比例", "组合成交ID",
    ]
    rows = []
    shares = 0
    cost = 0.0
    sequence = 0
    for audit in audit_rows:
        if audit.get("结果") != "实际成交" or audit.get("类型") not in ("买入", "卖出"):
            continue
        index = audit.get("K线索引")
        quantity = int(float(audit.get("成交股数", 0) or 0))
        price = float(audit.get("成交价", 0) or 0)
        if index is None or quantity < 100 or price <= 0:
            continue
        sequence += 1
        kind = str(audit["类型"])
        fee = float(audit.get("交易费用", 0) or 0)
        qfq_close = float(raw.iloc[index].get("前复权_收盘", price) or price)
        bfq_close = float(raw.iloc[index].get("不复权_收盘", price) or price)
        qfq_price = price * qfq_close / bfq_close if bfq_close > 0 else qfq_close
        pnl = None
        if kind == "买入":
            cost += price * quantity + fee
            shares += quantity
        else:
            sold = min(quantity, shares)
            average = cost / shares if shares > 0 else price
            pnl = price / average - 1 if average > 0 else 0.0
            if shares > 0:
                cost *= max(0.0, 1 - sold / shares)
            shares -= sold
            if shares <= 0:
                shares = 0
                cost = 0.0
        row = {
            "序号": sequence,
            "股票代码": stock,
            "持仓组ID": stock,
            "网格级别": audit.get("网格层级", 0),
            "时间": str(audit.get("时间", ""))[:16],
            "K线时间": str(raw.iloc[index].get("完整时间", ""))[:16],
            "K线索引": index,
            "类型": kind,
            "买入价": price if kind == "买入" else None,
            "卖出价": price if kind == "卖出" else None,
            "前复权成交价": qfq_price,
            "前复权买入价": qfq_price if kind == "买入" else None,
            "前复权卖出价": qfq_price if kind == "卖出" else None,
            "信号类型": audit.get("原因", "") if kind == "买入" else "",
            "卖出原因": audit.get("原因", "") if kind == "卖出" else "",
            "成交数量": quantity,
            "仓位": price * quantity,
            "交易费用": fee,
            "总成本": float(audit.get("成交净额", price * quantity) or price * quantity),
            "卖出净金额": float(audit.get("成交净额", price * quantity) or price * quantity) if kind == "卖出" else None,
            "盈亏比例": pnl,
            "组合成交ID": audit.get("成交ID", ""),
        }
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def _构建组合实际持仓(holding, raw, trades, audit_rows, initial_capital):
    state = holding.copy()
    if "K线索引" not in state.columns:
        state["K线索引"] = range(len(state))
    state_by_index = {int(row["K线索引"]): position for position, row in state.iterrows()}
    trade_by_index = {}
    for _, trade in trades.iterrows():
        trade_by_index.setdefault(int(trade["K线索引"]), []).append(trade)
    audit_by_index = {}
    for audit in audit_rows:
        if audit.get("K线索引") is not None:
            audit_by_index.setdefault(int(audit["K线索引"]), []).append(audit)

    cash = float(initial_capital)
    shares = 0
    cost = 0.0
    for index in range(len(raw)):
        for trade in trade_by_index.get(index, []):
            quantity = int(trade["成交数量"])
            price = float(trade["买入价"] if trade["类型"] == "买入" else trade["卖出价"])
            fee = float(trade.get("交易费用", 0) or 0)
            if trade["类型"] == "买入":
                cash -= price * quantity + fee
                cost += price * quantity + fee
                shares += quantity
            else:
                sold = min(quantity, shares)
                cash += float(trade.get("卖出净金额", price * sold) or price * sold)
                if shares > 0:
                    cost *= max(0.0, 1 - sold / shares)
                shares -= sold
                if shares <= 0:
                    shares = 0
                    cost = 0.0
        position = state_by_index.get(index)
        if position is None:
            continue
        close = float(raw.iloc[index].get("不复权_收盘", 0) or 0)
        market = shares * close
        state.at[position, "K线时间"] = str(raw.iloc[index].get("完整时间", ""))[:16]
        state.at[position, "当前现金"] = round(cash, 2)
        state.at[position, "持仓市值"] = round(market, 2)
        state.at[position, "权益"] = round(cash + market, 2)
        state.at[position, "持仓数量"] = shares
        approvals = audit_by_index.get(index, [])
        actual = next((row for row in approvals if row.get("结果") == "实际成交"), None)
        if actual:
            state.at[position, "最终动作"] = f"组合{actual['类型']}"
            state.at[position, "动作原因"] = str(actual.get("原因", "组合资金池批准成交"))
        elif approvals:
            state.at[position, "最终动作"] = str(approvals[0].get("结果", "组合未成交"))
            state.at[position, "动作原因"] = str(approvals[0].get("原因", "组合资金池未批准"))
        elif any(word in str(state.at[position, "最终动作"]) for word in ("买入", "卖出", "加仓")):
            state.at[position, "最终动作"] = "候选信号"
            state.at[position, "动作原因"] = "单股策略候选动作，未形成组合实际成交"
    return state


def 刷新多股单票回放(details, config_dir=None, portfolio_audit=None):
    """按组合实际成交按需生成单票回放，不改写候选交易证据。"""
    refreshed = 0
    config_snapshot = _读取配置快照(config_dir)
    for item in details:
        if "错误" in item:
            continue
        stock = str(item.get("股票代码", ""))
        result_dir = item.get("结果目录", "")
        holding_path = os.path.join(result_dir, "持仓过程.csv")
        raw_path = os.path.join(项目根目录, "数据模块", "raw", f"{stock}_双价格合并.pkl")
        if not all(os.path.isfile(candidate) for candidate in (holding_path, raw_path)):
            continue
        try:
            holding = pd.read_csv(holding_path, encoding="utf-8-sig")
            raw = _准备回放K线(pd.read_pickle(raw_path), holding)
            stock_audit = [
                row for row in (portfolio_audit or [])
                if str(row.get("股票代码", "")) == stock
            ]
            located_audit = _审计K线索引(stock_audit, raw)
            trades = _构建组合实际交易(stock, located_audit, raw)
            initial = float(item.get("初始资金", 0) or 0)
            actual_holding = _构建组合实际持仓(holding, raw, trades, located_audit, initial)
            trades.to_csv(os.path.join(result_dir, "组合实际成交.csv"), index=False, encoding="utf-8-sig")
            final_cash = float(actual_holding["当前现金"].iloc[-1]) if len(actual_holding) else initial
            final_equity = float(actual_holding["权益"].iloc[-1]) if len(actual_holding) else initial
            sells = trades[trades["类型"] == "卖出"] if not trades.empty else trades
            result = dict(item)
            result.update({
                "交易明细": trades,
                "持仓过程": actual_holding,
                "初始资金": initial,
                "最终现金": final_cash,
                "最终权益": final_equity,
                "总收益率": (final_equity / initial - 1) * 100 if initial else 0.0,
                "买入次数": int((trades["类型"] == "买入").sum()) if not trades.empty else 0,
                "卖出次数": int((trades["类型"] == "卖出").sum()) if not trades.empty else 0,
                "胜率": float((sells["盈亏比例"] > 0).mean() * 100) if len(sells) else 0.0,
                "数据行数": len(raw),
                "配置快照": config_snapshot,
                "运行参数": {"组合实际回放": True},
            })
            output = os.path.join(result_dir, "策略决策回放.html")
            if 生成报告(result, raw, 输出路径=output):
                refreshed += 1
        except (OSError, ValueError, KeyError, IndexError, TypeError, pd.errors.ParserError):
            continue
    return refreshed


def 运行多股回测(form):
    form = 提取模式配置(form, "multi")
    清理旧交互回测数据()
    stocks = 解析多股输入(form)
    run_dir = 创建运行目录("multi")
    config_dir = 复制配置(run_dir)
    应用表单到配置(config_dir, form)
    fallback_note = ""
    每股资金 = (
        float(form["base_position"])
        if form.get("portfolio_mode") == "shared_grid"
        else float(form["capital"]) / max(len(stocks), 1)
    )
    stock_dirs = {}
    for stock in stocks:
        stock_dirs[stock] = os.path.join(run_dir, "股票", stock)
        os.makedirs(stock_dirs[stock], exist_ok=True)
    details = [
        执行多股任务((stock, config_dir, form["start"], form["end"], 每股资金, form["liquidity_limit"], stock_dirs[stock]))
        for stock in stocks
    ] if int(form["workers"]) <= 1 else None
    if details is None:
        tasks = [(stock, config_dir, form["start"], form["end"], 每股资金, form["liquidity_limit"], stock_dirs[stock]) for stock in stocks]
        from concurrent.futures import ProcessPoolExecutor
        try:
            with ProcessPoolExecutor(max_workers=int(form["workers"])) as executor:
                details = list(executor.map(执行多股任务, tasks))
        except Exception:
            details = [执行多股任务(task) for task in tasks]
            fallback_note = "并行进程池启动失败，已自动降级为顺序执行，所以这次会更慢一些。"
    summary = 汇总多股结果(details)
    valid = [item for item in details if "错误" not in item]
    errors = [item for item in details if "错误" in item]
    组合初始资金 = float(form["capital"])
    if form.get("portfolio_mode") == "shared_grid":
        portfolio = 重放共享资金池网格(
            details,
            组合初始资金,
            max_positions=int(form["max_positions"]),
            max_single_ratio=float(form["max_single_ratio"]),
            max_total_ratio=float(form["max_total_ratio"]),
            cash_floor=float(form["cash_floor"]),
            stock_capital=float(form["base_position"]),
            grid_mode=form.get("grid_mode", "multiplier"),
            initial_position_ratio=float(form.get("grid_initial_ratio", 0.25) or 0.25),
            followup_position_ratio=float(form.get("grid_followup_ratio", 0.25) or 0.25),
            grid_multiplier=float(form.get("grid_multiplier", 2.0) or 2.0),
            max_add_count=int(form.get("grid_max_add_count", 5) or 5),
        )
        组合曲线 = portfolio["组合权益曲线"]
    else:
        portfolio = {}
        组合曲线 = 构建组合分析曲线(
            details, stocks, 组合初始资金, 每股资金, form["start"], form["end"]
        )
    峰值 = 组合初始资金
    组合回撤 = 0.0
    for point in 组合曲线:
        峰值 = max(峰值, point["权益"])
        组合回撤 = max(组合回撤, (峰值 - point["权益"]) / max(峰值, 1.0))
    组合最终权益 = 组合曲线[-1]["权益"] if 组合曲线 else 组合初始资金
    使用资金列表 = [point["持仓市值"] for point in 组合曲线]
    非零使用资金 = [value for value in 使用资金列表 if value > 0]
    summary.update({
        "资金模式": "共享资金池网格" if form.get("portfolio_mode") == "shared_grid" else "等额独立资金池",
        "网格加仓模式": form.get("grid_mode", "multiplier"),
        "组合初始资金": 组合初始资金,
        "组合最终权益": 组合最终权益,
        "组合总收益率": (组合最终权益 - 组合初始资金) / max(组合初始资金, 1.0),
        "组合最大回撤": 组合回撤,
        "最大使用资金": max(使用资金列表, default=0.0),
        "最小使用资金": min(非零使用资金, default=0.0),
    })
    if portfolio:
        summary.update({
            "资金审计": portfolio.get("资金审计", {}),
            "当前现金": portfolio.get("当前现金", 0.0),
            "当前持仓数量": portfolio.get("当前持仓数量", 0),
            "组合成交明细": portfolio.get("组合成交明细", []),
            "组合股票汇总": portfolio.get("组合股票汇总", {}),
        })
        audit_path = os.path.join(run_dir, "组合成交审计.csv")
        audit_rows = portfolio.get("组合成交明细", [])
        if audit_rows:
            import pandas as pd
            pd.DataFrame(audit_rows).to_csv(audit_path, index=False, encoding="utf-8-sig")
    output_path = os.path.join(run_dir, "多股回测结果.json")
    import json
    with open(output_path, "w", encoding="utf-8") as target:
        target.write(json.dumps({
            "股票列表": stocks,
            "开始日期": form["start"],
            "结束日期": form["end"],
            "初始资金": form["capital"],
            "每股资金池": 每股资金,
            "资金分配方式": summary["资金模式"],
            "资金审计": summary.get("资金审计", {}),
            "并行进程数": form["workers"],
            "RSI价格源": form["rsi_price_source"],
            "买入时机模式": form["entry_timing"],
            "汇总": summary,
            "股票明细": details,
            "组合权益曲线": 组合曲线,
        }, ensure_ascii=False, indent=2))
    multi_token = uuid.uuid4().hex
    multi_report_path = os.path.join(run_dir, "多股策略决策回放.html")
    生成多股策略回放页面(multi_report_path, multi_token, run_dir, details, summary, form, 组合曲线)
    最近多股报告.update({"token": multi_token, "path": multi_report_path, "run_dir": run_dir})
    return {
        "status": f"多股回测完成：{len(valid)}/{len(stocks)} 只股票有结果",
        "error": False,
        "metrics": {
            "total_return": 格式化小数百分比(summary.get("组合总收益率", 0)),
            "max_drawdown": f"{float(summary.get('组合最大回撤', 0)) * 100:.2f}%",
            "win_rate": f"{float(summary.get('加权胜率', 0)) * 100:.2f}%",
            "final_equity": f"{float(summary.get('组合最终权益', form['capital'])):,.0f}",
        },
        "report_url": f"/multi-report/{multi_token}",
        "run_dir": run_dir,
        "active_view": "interactive",
        "backtest_result": {
            "mode": "多股回测",
            "sample_count": f"{len(valid)}/{len(stocks)}",
            "output_name": os.path.basename(output_path),
            "rows": [
                {"label": "股票数量", "value": str(summary.get("股票数", 0))},
                {"label": "组合初始资金", "value": 格式化金额(summary.get("组合初始资金", form["capital"]))},
                {"label": "每股资金池", "value": 格式化金额(每股资金)},
                {"label": "资金模式", "value": summary["资金模式"]},
                {"label": "RSI价格源", "value": {"high": "最高价", "close": "收盘价", "low": "最低价"}.get(form["rsi_price_source"], form["rsi_price_source"])},
                {"label": "买入时机", "value": 买入时机名称(form["entry_timing"])},
                {"label": "买入总数", "value": str(summary.get("买入总数", 0))},
                {"label": "卖出总数", "value": str(summary.get("卖出总数", 0))},
                {"label": "总成交笔数", "value": str(summary.get("总交易数", 0))},
                {"label": "组合总收益率", "value": 格式化小数百分比(summary.get("组合总收益率", 0))},
                {"label": "组合最大回撤", "value": f"{float(summary.get('组合最大回撤', 0)) * 100:.2f}%"},
                {"label": "组合最终权益", "value": 格式化金额(summary.get("组合最终权益", form["capital"]))},
                {"label": "加权胜率", "value": f"{float(summary.get('加权胜率', 0)) * 100:.2f}%"},
                {"label": "平均盈亏比", "value": f"{float(summary.get('平均盈亏比', 0)):.3f}"},
                {"label": "收益回撤比", "value": f"{float(summary.get('收益回撤比', 0)):.3f}"},
                {"label": "综合得分", "value": f"{float(summary.get('综合得分', 0)):.3f}"},
                {"label": "失败股票数", "value": str(len(errors))},
                {"label": "组合层拦截", "value": str(sum(value for key, value in summary.get("资金审计", {}).items() if "拦截" in key))},
            ],
            "note": (
                ("本次多股回测按共享资金池网格运行，先由单股策略产生信号，再由组合层统一审批现金、仓位和持仓上限；"
                 if summary.get("资金模式") == "共享资金池网格" else
                 "本次多股回测按等额独立资金池运行，每只股票使用同一套单股交易逻辑；")
                + "详细K线、决策和组合曲线已保存。"
                + (f" {fallback_note}" if fallback_note else "")
            ),
        },
    }


def 获取当前单票回放地址(stock):
    return f"/output/K线回放_{stock}.html"


def 获取多股票回放地址():
    return "/output/多股票K线回放.html"


def 恢复最近多股报告():
    """服务重启后快速恢复最近一次完整多股回放。"""
    if not os.path.isdir(实验记录目录):
        return None
    candidates = []
    for name in os.listdir(实验记录目录):
        if not name.startswith("交互回测_") or not name.endswith("_multi"):
            continue
        run_dir = os.path.join(实验记录目录, name)
        result_path = os.path.join(run_dir, "多股回测结果.json")
        if not os.path.isfile(result_path):
            continue
        try:
            with open(result_path, encoding="utf-8") as source:
                payload = json.load(source)
            if not payload.get("股票明细") or not payload.get("汇总"):
                continue
            candidates.append((os.path.getmtime(result_path), run_dir, payload))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    if not candidates:
        return None

    _, run_dir, payload = max(candidates, key=lambda item: item[0])
    report_path = os.path.join(run_dir, "多股策略决策回放.html")
    if not os.path.isfile(report_path):
        return None

    # 回放 HTML 已在回测结束时生成。启动服务时只恢复链接状态，避免再次重放整批股票。
    import re
    try:
        with open(report_path, encoding="utf-8") as source:
            html = source.read()
    except OSError:
        return None
    match = re.search(r"/multi/([0-9a-f]+)/stock/", html)
    token = match.group(1) if match else uuid.uuid4().hex
    最近多股报告.update({"token": token, "path": report_path, "run_dir": run_dir})
    return report_path


@应用.route("/", methods=["GET", "POST"])
def 首页():
    form = 构建工作台表单() if request.method == "GET" else 规范化表单(request.form)
    result = 初始化结果()
    last_run_payload = 读取最近回测配置()
    last_run_form = last_run_payload.get("form", {}) if isinstance(last_run_payload, dict) else {}
    last_run_mode = last_run_payload.get("模式", "") if isinstance(last_run_payload, dict) else ""
    last_run_saved_at = last_run_payload.get("更新时间", "") if isinstance(last_run_payload, dict) else ""
    if request.method == "POST":
        try:
            if request.form.get("load_last_run") == "1":
                form = last_run_form if isinstance(last_run_form, dict) and last_run_form else 构建工作台表单()
                result["status"] = "已恢复上次回测实际配置；页面不会自动替换因子选择。"
            elif request.form.get("load_last") == "1":
                form = 构建工作台表单()
                result["status"] = "已恢复上次工作配置；如需开始回测，请确认参数后点击运行按钮。"
            elif request.form.get("reset") == "1":
                form = 构建默认表单()
                保存最近工作台配置(form)
                result["status"] = "已恢复正式默认值"
            elif request.form.get("apply_tb_single") == "1":
                form = 应用TB复刻参数(form, "single")
                result["status"] = "已应用TB复刻参数：最高价RSI买入、TB同根成交对照、最低价RSI下穿卖出。请再点击运行单股回测。"
            elif request.form.get("save_config") == "1":
                saved = 保存最近工作台配置(form)
                result["status"] = (
                    "当前单股和多股选择已保存；刷新页面后仍会保留。"
                    if saved else
                    f"保存失败：无法写入 {工作台配置路径}，当前页面选择未落盘。"
                )
                result["error"] = not saved
            elif request.form.get("run_mode") == "single":
                保存最近回测配置(form, "single")
                last_run_form, last_run_mode = copy.deepcopy(form), "single"
                last_run_saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                issues = 预检查无成交风险(form, "single")
                if issues:
                    result["status"] = "已拦截本次单股回测：参数存在明显无成交风险"
                    result["error"] = True
                    result["backtest_result"] = {
                        "mode": "单股预检查未通过",
                        "sample_count": str(form.get("single_stock") or "--"),
                        "output_name": "--",
                        "rows": [{"label": f"风险 {idx+1}", "value": issue} for idx, issue in enumerate(issues)],
                        "note": "请先调整上面的单股参数，再重新点击“运行单股回测”。",
                    }
                else:
                    result = 运行交互回测(form)
            elif request.form.get("run_mode") == "multi":
                保存最近回测配置(form, "multi")
                last_run_form, last_run_mode = copy.deepcopy(form), "multi"
                last_run_saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                issues = 预检查无成交风险(form, "multi")
                if issues:
                    result["status"] = "已拦截本次多股回测：参数存在明显无成交风险"
                    result["error"] = True
                    result["backtest_result"] = {
                        "mode": "多股预检查未通过",
                        "sample_count": "多股",
                        "output_name": "--",
                        "rows": [{"label": f"风险 {idx+1}", "value": issue} for idx, issue in enumerate(issues)],
                        "note": "请先调整上面的多股参数，再重新点击“运行多股回测”。",
                    }
                else:
                    result = 运行多股回测(form)
            else:
                result = 运行交互回测(form)
        except Exception as error:  # pragma: no cover - 异常分支依赖真实数据/环境
            result["status"] = f"运行失败：{error}"
            result["error"] = True
        finally:
            # 无论回测成功、预检查拦截还是异常，都保留用户刚刚提交的选择。
            保存最近工作台配置(form)
    elif 最近报告["token"]:
        snapshot = 读取单股回测摘要(最近报告["run_dir"])
        stock = snapshot.get("股票代码", os.path.basename(最近报告["run_dir"] or "").split("_")[-1])
        result["status"] = f"已恢复最近一次单股回测：{stock}（主页面与回放使用同一快照）"
        result["report_url"] = url_for("查看报告", token=最近报告["token"])
        result["run_dir"] = 最近报告["run_dir"]
        result["active_view"] = "stock"
        result["metrics"] = {
            "total_return": snapshot.get("总收益率", "--"),
            "max_drawdown": snapshot.get("最大回撤", "--"),
            "win_rate": snapshot.get("胜率", "--"),
            "final_equity": snapshot.get("最终权益", "--"),
        }
        result["backtest_result"] = {
            "mode": "单股回测（已恢复）",
            "sample_count": stock,
            "output_name": os.path.basename(最近报告["run_dir"] or "--"),
            "rows": [
                {"label": "股票代码", "value": stock},
                {"label": "时间区间", "value": snapshot.get("数据行数", "--") + " 根K线"},
                {"label": "买卖次数", "value": snapshot.get("交易次数", "--")},
                {"label": "总收益率", "value": snapshot.get("总收益率", "--")},
            ],
            "note": "当前单票回放与最新报告均直接读取此回测目录的同一份报告。",
        }
        # 页面重启后仍尽量恢复最近一次的成交诊断（CSV 是持仓过程的持久快照）。
        process_path = os.path.join(最近报告["run_dir"] or "", "持仓过程.csv")
        try:
            with open(process_path, "r", encoding="utf-8-sig", newline="") as source:
                result["backtest_result"]["diagnostics"] = 构建成交诊断({"持仓过程": list(csv.DictReader(source))}, None, "single")
        except (OSError, csv.Error):
            result["backtest_result"]["diagnostics"] = None
    config_summary = 工作台配置摘要(form, "single") + 工作台配置摘要(form, "multi")
    last_run_summary = (
        工作台配置摘要(last_run_form, last_run_mode)
        if last_run_mode in ("single", "multi") and isinstance(last_run_form, dict)
        else []
    )
    return render_template_string(
        页面模板,
        form=form,
        single_module_groups=模块分组字段(form, "single"),
        multi_module_groups=模块分组字段(form, "multi"),
        status=result["status"],
        error=result["error"],
        metrics=result["metrics"],
        report_url=result["report_url"],
        run_dir=result["run_dir"],
        active_view=result["active_view"],
        # 不能再使用按股票代码固定命名的静态页；它可能属于更早的一次回测。
        # 当前单票回放与“最新报告”必须引用完全相同的结果快照。
        current_stock_url=(
            url_for("查看报告", token=最近报告["token"])
            if 最近报告["token"] else 获取当前单票回放地址(form["single_stock"])
        ),
        multi_stock_url=(
            f"/multi-report/{最近多股报告['token']}"
            if 最近多股报告["token"] else 获取多股票回放地址()
        ),
        backtest_result=result["backtest_result"],
        config_summary=config_summary,
        config_saved_at=读取工作台配置时间(),
        last_run_summary=last_run_summary,
        last_run_saved_at=last_run_saved_at,
        last_run_mode="单股" if last_run_mode == "single" else "多股" if last_run_mode == "multi" else "",
    )


@应用.route("/report/<token>")
def 查看报告(token):
    if token != 最近报告["token"] or not 最近报告["path"] or not os.path.exists(最近报告["path"]):
        return Response("报告不存在或已失效。", status=404, content_type="text/plain; charset=utf-8")
    with open(最近报告["path"], encoding="utf-8") as source:
        return Response(source.read(), content_type="text/html; charset=utf-8")


@应用.route("/multi-report/<token>")
def 查看多股报告(token):
    if token != 最近多股报告["token"] or not 最近多股报告["path"] or not os.path.exists(最近多股报告["path"]):
        return Response("多股报告不存在或已失效。", status=404, content_type="text/plain; charset=utf-8")
    with open(最近多股报告["path"], encoding="utf-8") as source:
        return Response(source.read(), content_type="text/html; charset=utf-8")


@应用.route("/multi/<token>/stock/<stock>")
def 查看多股单票回放(token, stock):
    if token != 最近多股报告["token"] or not 最近多股报告["run_dir"]:
        return Response("多股回放不存在或已失效。", status=404, content_type="text/plain; charset=utf-8")
    safe_stock = "".join(ch for ch in str(stock) if ch.isalnum() or ch in "_-" )
    path = os.path.join(最近多股报告["run_dir"], "股票", safe_stock, "策略决策回放.html")
    result_path = os.path.join(最近多股报告["run_dir"], "多股回测结果.json")
    template_path = os.path.join(项目根目录, "回测引擎", "kline_template.html")
    needs_refresh = (
        not os.path.isfile(path)
        or os.path.getmtime(path) < os.path.getmtime(template_path)
        or os.path.getmtime(path) < os.path.getmtime(result_path)
    )
    if needs_refresh:
        try:
            with open(result_path, encoding="utf-8") as source:
                payload = json.load(source)
            detail = next((item for item in payload.get("股票明细", []) if str(item.get("股票代码")) == safe_stock), None)
            if detail:
                audit = payload.get("汇总", {}).get("组合成交明细", [])
                刷新多股单票回放(
                    [detail],
                    os.path.join(最近多股报告["run_dir"], "配置快照_交互"),
                    audit,
                )
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    if not os.path.isfile(path):
        return Response("该股票没有可用回放。", status=404, content_type="text/plain; charset=utf-8")
    with open(path, encoding="utf-8") as source:
        return Response(source.read(), content_type="text/html; charset=utf-8")


@应用.route("/output/<path:filename>")
def 查看输出文件(filename):
    return send_from_directory(输出目录, filename)


# 进程重启不应让“当前单票回放”退回到一个过期的静态文件。
恢复最近单票报告()
恢复最近多股报告()


def main():
    parser = argparse.ArgumentParser(description="启动策略0717交互回测页面")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--no-open", action="store_true", help="启动后不自动打开浏览器")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"
    print(f"回测主页面：{url}")

    # 先做一次“能否监听端口”的快速预检查：有些受限沙盒会在 bind/listen 时直接拦截并退出，
    # 而 Flask/werkzeug 的错误信息可能只显示为一行 “Operation not permitted”。
    try:
        family = socket.AF_INET6 if ":" in args.host else socket.AF_INET
        probe = socket.socket(family, socket.SOCK_STREAM)
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind((args.host, args.port))
        probe.listen(1)
    except OSError as exc:
        errno = getattr(exc, "errno", None)
        if errno in (1, 13):  # EPERM / EACCES
            print(
                "启动失败：当前环境不允许监听本地端口（Operation not permitted / Permission denied）。\n"
                "建议：\n"
                "1) 用你自己的系统终端直接在项目根目录运行本命令；不要在受限/托管沙盒里启动。\n"
                "2) 如果你要用其他设备访问，请改用 --host 0.0.0.0 并在浏览器打开你的局域网IP。\n"
                "3) 如果是企业/系统安全策略拦截，请允许 Python 接受本地连接或换一台可监听端口的环境。"
            )
            raise SystemExit(1) from exc
        if errno in (48, 98):  # macOS/Linux EADDRINUSE
            print(
                f"启动失败：端口已被占用（{args.port}）。\n"
                "建议：换一个端口（例如 --port 8510），或关闭占用该端口的进程。"
            )
            raise SystemExit(1) from exc
        raise
    finally:
        try:
            probe.close()
        except Exception:
            pass

    if not args.no_open:
        webbrowser.open(url)
    try:
        应用.run(host=args.host, port=args.port, debug=False)
    except SystemExit as exc:
        code = getattr(exc, "code", None)
        message = str(code) if code is not None else str(exc)
        if isinstance(code, OSError):
            errno = getattr(code, "errno", None)
            message = str(code)
        else:
            errno = None

        # werkzeug 可能会捕获 OSError 并直接 sys.exit(str(error))，导致这里只能看到 SystemExit。
        if errno in (1,) or "Operation not permitted" in message:
            print(
                "启动失败：当前环境不允许监听本地端口（Operation not permitted）。\n"
                "建议：\n"
                "1) 用你自己的系统终端直接在项目根目录运行本命令；不要在受限/托管沙盒里启动。\n"
                "2) 如果你要用其他设备访问，请改用 --host 0.0.0.0 并在浏览器打开你的局域网IP。\n"
                "3) 如果是企业/系统安全策略拦截，请允许 Python 接受本地连接或换一台可监听端口的环境。"
            )
            raise SystemExit(1) from exc
        if errno in (48,) or "Address already in use" in message:
            print(
                f"启动失败：端口已被占用（{args.port}）。\n"
                "建议：换一个端口（例如 --port 8510），或关闭占用该端口的进程。"
            )
            raise SystemExit(1) from exc
        raise
    except OSError as exc:
        errno = getattr(exc, "errno", None)
        if errno in (1,):  # EPERM: Operation not permitted（常见于受限沙盒/托管运行环境）
            print(
                "启动失败：当前环境不允许监听本地端口（Operation not permitted）。\n"
                "建议：\n"
                "1) 用你自己的系统终端直接在项目根目录运行本命令；不要在受限/托管沙盒里启动。\n"
                "2) 如果你要用其他设备访问，请改用 --host 0.0.0.0 并在浏览器打开你的局域网IP。\n"
                "3) 如果是企业/系统安全策略拦截，请允许 Python 接受本地连接或换一台可监听端口的环境。"
            )
            raise SystemExit(1) from exc
        if errno in (48,):  # macOS EADDRINUSE
            print(
                f"启动失败：端口已被占用（{args.port}）。\n"
                "建议：换一个端口（例如 --port 8510），或关闭占用该端口的进程。"
            )
            raise SystemExit(1) from exc
        raise


if __name__ == "__main__":
    main()
