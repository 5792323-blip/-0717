# report_generator.py
import os, sys, json
import numpy as np
import pandas as pd
from datetime import datetime
项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 项目根目录)
模板路径 = os.path.join(项目根目录, '回测引擎', 'kline_template.html')
from 策略引擎.反推因子 import 智能反推
def _加载数据(股票代码='600519'):
    try:
        from 数据模块.股票加载器 import 加载股票
        return 加载股票(股票代码, '双价格合并')
    except Exception as e:
        print(f'无法加载K线数据: {e}')
        return None

def 生成报告(回测结果, 原始K线数据=None, 输出路径=None):
    if 回测结果 is None:
        return None
    股票代码 = 回测结果.get('股票代码', 'unknown')
    if 输出路径 is None:
        # 单股票回放固定为一个文件，新的回测直接覆盖旧页面。
        输出路径 = os.path.join(项目根目录, '9_输出', f'K线回放_{股票代码}.html')
    os.makedirs(os.path.dirname(输出路径), exist_ok=True)
    if not os.path.exists(模板路径):
        print('找不到模板:', 模板路径)
        return None
    with open(模板路径, 'r', encoding='utf-8') as f:
        html = f.read()
    k线记录 = []
    _初始资金 = 0
    _权益JSON = '[]'
    # 交易数据JSON
    交易明细 = 回测结果['交易明细']
    交易JSON = '[]'
    交易记录 = []
    if len(交易明细) > 0:
        交易记录 = []
        for _, row in 交易明细.iterrows():
            d = {}
            for col in 交易明细.columns:
                val = row[col]
                if pd.isna(val):
                    d[col] = None
                else:
                    try:
                        d[col] = float(val)
                    except (ValueError, TypeError):
                        d[col] = str(val)
            交易记录.append(d)
        交易JSON = json.dumps(交易记录, ensure_ascii=False, default=str)
    # K线数据JSON
    K线JSON = '[]'
    if 原始K线数据 is not None and len(原始K线数据) > 0:
        cols = [c for c in ['日期','前复权_开盘','前复权_最高','前复权_最低','前复权_收盘','不复权_开盘','不复权_最高','不复权_最低','不复权_收盘','RSI_14','RSI_最高价','RSI_收盘价','RSI_最低价','RSI_均线_20','ATR_14'] if c in 原始K线数据.columns]
        if '前复权_收盘' in 原始K线数据.columns and len(cols) >= 3:
            # 反推价和哨兵价必须跟随回测所选 RSI 价格源。RSI_14 是兼容字段，
            # 这里仍显式选择高/收/低价，避免报告层固定使用收盘价。
            _技术参数 = (回测结果.get('配置快照', {}) or {}).get('参数配置.yaml', {}).get('技术指标参数', {})
            _rsi_source = str(_技术参数.get('RSI价格源', 'close') or 'close').lower()
            _source_qfq = {'high': '前复权_最高', 'close': '前复权_收盘', 'low': '前复权_最低'}
            _source_bfq = {'high': '不复权_最高', 'close': '不复权_收盘', 'low': '不复权_最低'}
            _rsi_price_col = _source_qfq.get(_rsi_source, '前复权_收盘')
            _rsi_bfq_col = _source_bfq.get(_rsi_source, '不复权_收盘')
            prices = 原始K线数据[_rsi_price_col].values
            rsi_ma_col = 'RSI_均线_20' if 'RSI_均线_20' in 原始K线数据.columns else None
            rsi_ma_values = 原始K线数据[rsi_ma_col].values if rsi_ma_col else None
            # 构建反推哨兵价查询表（从持仓过程中提取）
            _持仓过程_df = 回测结果.get('持仓过程', None)
            反推哨兵价查询 = {}
            真实K线状态查询 = {}
            if _持仓过程_df is not None and len(_持仓过程_df) > 0:
                import json as _json
                for _ft_idx, _ft_row in _持仓过程_df.iterrows():
                    _ft_str = _ft_row.get('反推哨兵价列表', '[]')
                    if isinstance(_ft_str, str):
                        try:
                            反推哨兵价查询[int(_ft_row['K线索引'])] = _json.loads(_ft_str)
                        except:
                            反推哨兵价查询[int(_ft_row['K线索引'])] = []
                    elif isinstance(_ft_str, list):
                        反推哨兵价查询[int(_ft_row['K线索引'])] = _ft_str
                    真实K线状态查询[int(_ft_row['K线索引'])] = _ft_row.to_dict()
            # 构建买入/卖出时间映射
            _买入时间映射 = {}
            _买入哨兵价映射 = {}
            _卖出时间集合 = set()
            _交易明细_df = 回测结果.get('交易明细', None)
            if _交易明细_df is not None and len(_交易明细_df) > 0:
                for _, _交易 in _交易明细_df.iterrows():
                    try:
                        _交易时间 = str(_交易['时间']).strip()[:16]
                        if _交易['类型'] == '买入':
                            _买入时间映射[_交易时间] = str(_交易.get('信号类型', ''))
                            _买入哨兵价映射[_交易时间] = _交易.get('哨兵价', None)
                        elif _交易['类型'] == '卖出':
                            _卖出时间集合.add(_交易时间)
                    except:
                        pass
            # 交易CSV常只有日期；以引擎持仓过程中的真实“买入/卖出”动作定位唯一K线。
            真实成交索引 = {}
            for _state_idx, _state in 真实K线状态查询.items():
                _action = str(_state.get('最终动作', '') or '')
                if '买入' in _action or '卖出' in _action:
                    _kind = '买入' if '买入' in _action else '卖出'
                    _day = str(_state.get('日期', '') or '')[:10]
                    _seq = _state.get('买入序号')
                    _group = _state.get('持仓组ID')
                    try:
                        _seq = None if pd.isna(_seq) else str(int(float(_seq)))
                    except (TypeError, ValueError):
                        _seq = None
                    真实成交索引.setdefault((_day, _kind), []).append({
                        '索引': int(_state_idx),
                        '序号': _seq,
                        '持仓组ID': None if pd.isna(_group) else str(_group),
                    })
            used_action_indexes = set()
            enriched_records = []
            for record in 交易记录:
                day = str(record.get('时间', '') or '')[:10]
                kind = str(record.get('类型', '') or '')
                seq = record.get('序号')
                try:
                    seq = None if seq is None else str(int(float(seq)))
                except (TypeError, ValueError):
                    seq = None
                group = record.get('持仓组ID')
                group = None if group is None else str(group)
                candidates = 真实成交索引.get((day, kind), [])
                match = next((item for item in candidates if item['索引'] not in used_action_indexes and seq and item['序号'] == seq), None)
                if match is None:
                    match = next((item for item in candidates if item['索引'] not in used_action_indexes and group and item['持仓组ID'] == group), None)
                if match is None:
                    match = next((item for item in candidates if item['索引'] not in used_action_indexes), None)
                if match is not None:
                    record['K线索引'] = match['索引']
                    used_action_indexes.add(match['索引'])
                enriched_records.append(record)
            交易记录 = enriched_records
            交易JSON = json.dumps(交易记录, ensure_ascii=False, default=str)
            k线记录 = []
            # ★ 权益曲线（直接从原始K线+Trades计算）
            _初始资金 = float(回测结果.get('初始资金', 0) or 0)
            结果最终现金 = 回测结果.get('最终现金', 0)
            if _初始资金 <= 0:
                _初始资金 = float(回测结果.get('配置快照', {}).get('仓位配置.yaml', {}).get('基准仓位', {}).get('初始资金', 0) or 0)
            if _初始资金 <= 0:
                _初始资金 = 1000000
            _当前现金 = _初始资金
            _当前持股 = 0
            _权益列表 = []
            # 按持仓组关联买卖；兼容旧结果时回退到序号。
            _买入记录 = {}  # {序号: {时间, 价, 金额, 组}}
            _卖出记录 = {}  # {序号: {时间, 价, 金额}}
            _买入组 = {}
            _待卖出组 = {}
            if _交易明细_df is not None and len(_交易明细_df) > 0:
                for _, _r in _交易明细_df.iterrows():
                    try:
                        _seq = int(_r['序号'])
                        _tp = str(_r['类型'])
                        _group = str(_r.get('持仓组ID', _seq))
                        if _tp == '买入':
                            _p = float(_r['买入价']) if not pd.isna(_r.get('买入价')) else 0
                            _amt = float(_r['仓位']) if not pd.isna(_r.get('仓位')) else 0
                            if _p > 0 and _amt > 0:
                                _买入记录[_seq] = {'时间': str(_r['时间']).strip()[:16], '价': _p, '金额': _amt, '组': _group}
                                _买入组.setdefault(_group, []).append(_seq)
                        elif _tp == '卖出':
                            _卖价 = float(_r['卖出价']) if not pd.isna(_r.get('卖出价')) else 0
                            _盈亏 = float(_r['盈亏比例']) if not pd.isna(_r.get('盈亏比例')) else 0
                            _卖金额 = _买入记录[_seq]['金额'] * (1 + _盈亏)
                            _待卖出组[_group] = {'时间': str(_r['时间']).strip()[:16], '价': _卖价, '盈亏': _盈亏}
                    except: pass# 哨兵价跟踪变量
            for _group, _sell in _待卖出组.items():
                for _seq in _买入组.get(_group, []):
                    _buy = _买入记录.get(_seq)
                    if _buy:
                        _卖出记录[_seq] = {
                            '时间': _sell['时间'], '价': _sell['价'],
                            '金额': _buy['金额'] * (1 + _sell['盈亏'])
                        }
            _哨兵价当前 = None
            _上次反推目标RSI = None
            _前一根K最高价 = None
            _前RSI = None
            _已形成哨兵价 = False
            _前一根哨兵价 = None
            for idx, row in 原始K线数据[cols].iterrows():
                完整时间_ = str(idx) if hasattr(idx, 'strftime') else str(idx)
                完整时间_ = 完整时间_[:16]
                d = {}
                for col in cols:
                    val = row[col]
                    if pd.isna(val):
                        d[col] = None
                    else:
                        try:
                            d[col] = float(val)
                        except:
                            d[col] = str(val)
                if hasattr(idx, 'strftime'):
                    d['完整时间'] = idx.strftime('%Y-%m-%d %H:%M')
                else:
                    d['完整时间'] = str(idx)
                # 反推价计算
                i = len(k线记录)
                _是买入K线 = d['完整时间'] in _买入时间映射
                if i >= 14 and rsi_ma_values is not None and (rsi_ma_values[i-1] is None or (not np.isnan(rsi_ma_values[i-1]))):
                   if _是买入K线 and i >= 15:
                       前窗口 = prices[i-15:i]
                       if not np.any(np.isnan(前窗口)):
                        if i >= 1 and rsi_ma_values[i-1] is not None and not np.isnan(rsi_ma_values[i-1]):
                            前rsi_ma_prev = float(rsi_ma_values[i-1])
                        else:
                            前rsi_ma_prev = None
                        前结果 = 智能反推(前窗口, RSI_MA_上一根=前rsi_ma_prev)
                        ft_qfq = 前结果.get('目标价位')
                        d['反推价'] = ft_qfq
                        d['反推价_前复权'] = ft_qfq
                        d['反推信号'] = 前结果.get('选择逻辑', '') if 前结果.get('选择逻辑') else None
                        d['反推目标RSI'] = 前结果.get('目标RSI')
                        d['涨跌方向'] = 前结果.get('涨跌方向')
                        bfq_source = float(原始K线数据[_rsi_bfq_col].values[i])
                        d['反推价_不复权'] = round(ft_qfq / (float(prices[i]) / bfq_source), 2) if ft_qfq and bfq_source > 0 else None
                       else:
                           d['反推价'] = None; d['反推信号'] = None; d['反推目标RSI'] = None
                   else:
                       窗口 = prices[i-14:i+1]
                       if len(窗口) == 15 and not np.any(np.isnan(窗口)):
                        rsi_ma_prev = float(rsi_ma_values[i-1])
                        结果 = 智能反推(窗口, RSI_MA_上一根=rsi_ma_prev)
                        ft_qfq = 结果.get('目标价位')
                        d['反推价'] = ft_qfq
                        d['反推价_前复权'] = ft_qfq
                        d['反推信号'] = 结果.get('选择逻辑', '') if 结果.get('选择逻辑') else None
                        d['反推目标RSI'] = 结果.get('目标RSI')
                        d['涨跌方向'] = 结果.get('涨跌方向')
                        bfq_source = float(原始K线数据[_rsi_bfq_col].values[i])
                        d['反推价_不复权'] = round(ft_qfq / (float(prices[i]) / bfq_source), 2) if ft_qfq and bfq_source > 0 else None
                       else:
                           d['反推价'] = None; d['反推信号'] = None; d['反推目标RSI'] = None
                else:
                    d['反推价'] = None
                    d['反推信号'] = None
                    d['反推目标RSI'] = None
                # 从持仓过程中提取反推哨兵价
                if _持仓过程_df is not None and len(反推哨兵价查询) > 0:
                    _ft_list = 反推哨兵价查询.get(i, [])
                    if _ft_list:
                        d['反推哨兵价列表'] = _ft_list
               # ─── 阶梯式哨兵价 ───
                # 哨兵价独立于买卖，只基于RSI阈值突破
                _当前反推目标 = d.get('反推目标RSI', None)
                _前复权高 = row.get('前复权_最高', None)
                if _前复权高 is not None and not pd.isna(_前复权高):
                    _前复权高 = float(_前复权高)
                else:
                    _前复权高 = None
                _反推价 = d.get('反推价', None)
                if _反推价 is not None:
                    _反推价 = float(_反推价)
                # 检测反推目标RSI向上跳变（RSI上穿阈值）
                _阈值上穿 = False
                if (_上次反推目标RSI is not None and _当前反推目标 is not None
                    and not pd.isna(_当前反推目标) and not pd.isna(_上次反推目标RSI)):
                    _差 = float(_当前反推目标) - float(_上次反推目标RSI)
                    if _差 > 0.01:  # 向上跳变 → RSI上穿
                        _阈值上穿 = True
                # ─── 哨兵价（基于RSI实际阈值上穿）───
                # 每当RSI实际数值上穿阈值(20/MA/30/70)时形成新哨兵价
                # 哨兵价 = max(反推价(at上穿阈值), 上一根K线最高价)
                # 只有价格真正突破当前哨兵价才上移；新预挂信号不能覆盖有效值。
                _当前RSI = row.get('RSI_14', None)
                if _当前RSI is not None and not pd.isna(_当前RSI):
                    _当前RSI = float(_当前RSI)
                else:
                    _当前RSI = None
                _前复权高 = row.get('前复权_最高', None)
                if _前复权高 is not None and not pd.isna(_前复权高):
                    _前复权高 = float(_前复权高)
                else:
                    _前复权高 = None
                # 检测RSI阈值上穿
                _上穿阈值 = None
                if _前RSI is not None and _当前RSI is not None:
                    if _前RSI < 20 and _当前RSI >= 20:
                        _上穿阈值 = 20
                    elif i > 0 and rsi_ma_values is not None and not np.isnan(rsi_ma_values[i-1]) and _前RSI < float(rsi_ma_values[i-1]) and _当前RSI >= float(rsi_ma_values[i-1]):
                        _上穿阈值 = float(rsi_ma_values[i-1])
                    elif _前RSI < 30 and _当前RSI >= 30:
                        _上穿阈值 = 30
                    elif _前RSI < 70 and _当前RSI >= 70:
                        _上穿阈值 = 70
                _本根哨兵价说明 = None
                if _上穿阈值 is not None and i >= 14:
                    from 策略引擎.反推因子 import 反推RSI价位
                    _窗口 = prices[i-14:i+1]
                    if len(_窗口) == 15 and not np.any(np.isnan(_窗口)):
                        _结果 = 反推RSI价位(_窗口, 目标RSI=_上穿阈值)
                        _反推价上穿 = _结果.get('目标价位')
                        if _反推价上穿 is not None:
                            _反推价上穿 = float(_反推价上穿)
                            if _前一根K最高价 is not None:
                                _哨兵价当前 = max(_反推价上穿, _前一根K最高价)
                            else:
                                _哨兵价当前 = _反推价上穿
                            _已形成哨兵价 = True
                            _本根哨兵价说明 = (
                                f"本根新形成：{_上穿阈值} 上穿，"
                                f"反推价 {round(_反推价上穿, 2)}，"
                                f"最终哨兵 {round(_哨兵价当前, 2)}"
                            )
                if _本根哨兵价说明 is None and _哨兵价当前 is not None:
                    if _前一根哨兵价 is None:
                        _本根哨兵价说明 = "当前已有哨兵价"
                    elif float(_哨兵价当前) > float(_前一根哨兵价):
                        _本根哨兵价说明 = (
                            f"跟踪上移：{round(_前一根哨兵价, 2)} → "
                            f"{round(_哨兵价当前, 2)}"
                        )
                    else:
                        _本根哨兵价说明 = "保持不变：未出现新的 RSI 上穿信号"
                # 报告层仅作旧数据兜底；真实回测状态会在下方覆盖此字段。
                if _哨兵价当前 is not None and not (isinstance(_哨兵价当前, float) and (np.isnan(_哨兵价当前) or pd.isna(_哨兵价当前))):
                    d['哨兵价'] = round(_哨兵价当前, 2)
                else:
                    d['哨兵价'] = None
                d['哨兵价状态'] = _本根哨兵价说明
                d['哨兵价前值'] = round(_前一根哨兵价, 2) if _前一根哨兵价 is not None else None
                # 更新跟踪变量
                _前一根哨兵价 = _哨兵价当前
                _前一根K最高价 = _前复权高
                _前RSI = _当前RSI
                # ★ 权益曲线（逐K线计算）
                _前复权收盘价 = d.get('前复权_收盘', None)
                if _前复权收盘价 is not None and (isinstance(_前复权收盘价, float) and pd.isna(_前复权收盘价)):
                    _前复权收盘价 = None
                # 按序号匹配当前K线的买卖
                for _seq_no, _buy in list(_买入记录.items()):
                    if _buy['时间'] == 完整时间_:
                        _股数 = max(0, int(_buy['金额'] / _buy['价'] / 100) * 100)
                        _当前持股 += _股数
                        _当前现金 -= _股数 * _buy['价']
                        break
                for _seq_no, _sell in _卖出记录.items():
                    if _sell['时间'] == 完整时间_:
                        _当前现金 += _sell['金额']
                        if _seq_no in _买入记录:
                            _原股数 = max(0, int(_买入记录[_seq_no]['金额'] / _买入记录[_seq_no]['价'] / 100) * 100)
                            _当前持股 = max(0, _当前持股 - _原股数)
                        break
                if _当前持股 > 0 and _前复权收盘价 and _前复权收盘价 > 0:
                    _当前权益 = _当前现金 + _当前持股 * _前复权收盘价
                else:
                    _当前权益 = _当前现金
                d['权益'] = round(_当前权益, 2) if not (isinstance(_当前权益, float) and (pd.isna(_当前权益) or np.isnan(_当前权益))) else _当前现金
                # 优先使用回测引擎实际记录的决策和账户状态。
                _真实状态 = 真实K线状态查询.get(i, {})
                for _字段 in ['买入信号', '过滤检查', '卖出检查', '决策记录', '最终动作', '动作原因', '成交拒绝原因', '当前现金', '持仓市值', '权益', '持仓数量', '哨兵价', '哨兵价状态', '哨兵价前值', '本根触发哨兵价', '哨兵价形成类型', '哨兵价本根新形成', '哨兵价已确认可执行', '本根反推价', '本根反推信号类型', '本根反推目标RSI', 'RSI反推价当前', '上一根突破基准价当前', '最终买入触发价当前', '哨兵价锁定信号类型']:
                    if _字段 in _真实状态 and not pd.isna(_真实状态[_字段]):
                        d[_字段] = _真实状态[_字段]
                # 若本根真实形成了新哨兵，状态说明必须使用引擎真实字段，
                # 不再使用报告层重新反推得到的近似值。
                if d.get('哨兵价本根新形成') and d.get('本根反推价') is not None:
                    _类型 = d.get('本根反推信号类型') or d.get('哨兵价形成类型') or 'RSI信号'
                    d['哨兵价状态'] = (
                        f"本根新形成：{_类型}，反推价 {float(d['本根反推价']):.2f}，"
                        f"最终哨兵 {float(d.get('哨兵价') or d['本根反推价']):.2f}"
                    )
                d['完整时间'] = 完整时间_
                k线记录.append(d)
            K线JSON = json.dumps(k线记录, ensure_ascii=False, default=str)
    # 权益JSON
    _权益JSON = json.dumps([(None if (v is not None and pd.isna(v)) else v) for v in [r.get('权益') for r in k线记录]], ensure_ascii=False)
    
    for k, v in {
        '%%股票代码%%': 股票代码,
        '%%交易JSON%%': 交易JSON,
        '%%K线JSON%%': K线JSON,
        '%%数据行数%%': str(回测结果.get('数据行数', 0)),
        '%%买入次数%%': str(回测结果.get('买入次数', 0)),
        '%%卖出次数%%': str(回测结果.get('卖出次数', 0)),
        '%%胜率%%': f"{回测结果.get('胜率', 0):.1f}",
        '%%总收益率%%': f"{回测结果.get('总收益率', 0):+.2f}",
        '%%最终现金%%': f"{回测结果.get('最终现金', 0):,.0f}",
        '%%初始资金%%': f"{_初始资金:.0f}",
        '%%权益JSON%%': _权益JSON,
        '%%基准JSON%%': json.dumps({
            'strategy': [r.get('权益') for r in k线记录],
            'stock': 回测结果.get('基准_个股买入持有', []),
            'hs300': 回测结果.get('基准_HS300', []),
        }, ensure_ascii=False, default=str),
        '%%配置JSON%%': json.dumps(回测结果.get('配置快照', {}), ensure_ascii=False, default=str),
        '%%耗时%%': f"{回测结果.get('耗时', 0):.1f}",
    }.items():
        html = html.replace(k, str(v))
    if '单股全仓模式' in 回测结果.get('运行参数', {}):
        html = html.replace('%%运行模式%%', '单股全仓模式' if 回测结果['运行参数'].get('单股全仓模式') else '常规仓位模式')
    else:
        html = html.replace('%%运行模式%%', '常规仓位模式')
    with open(输出路径, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'K线回放报告: {输出路径}')
    print(f'大小: {os.path.getsize(输出路径)/1024:.0f}KB')
    return 输出路径
if __name__ == '__main__':
    实验目录 = os.path.join(项目根目录, '10_实验记录')
    if not os.path.exists(实验目录):
        print('请先运行回测'); sys.exit(1)
    候选实验 = [
        os.path.join(实验目录, name)
        for name in os.listdir(实验目录)
        if os.path.isfile(os.path.join(实验目录, name, '交易明细.csv'))
    ]
    if not 候选实验:
        print('请先运行回测'); sys.exit(1)
    # 实验目录中也会有训练与分析产物；只从真实回测结果里选择最近一份。
    最新实验 = max(候选实验, key=lambda path: os.path.getmtime(path))
    交易文件 = os.path.join(最新实验, '交易明细.csv')
    摘要文件 = os.path.join(最新实验, '回测摘要.txt')
    if not os.path.exists(交易文件):
        print(f'找不到: {交易文件}'); sys.exit(1)
    交易明细 = pd.read_csv(交易文件, encoding='utf-8-sig')
    持仓过程 = pd.read_csv(os.path.join(最新实验, '持仓过程.csv'), encoding='utf-8-sig') if os.path.exists(os.path.join(最新实验, '持仓过程.csv')) else pd.DataFrame()
    import re
    股票匹配 = re.search(r'_(\d{6})$', os.path.basename(最新实验))
    股票代码 = 股票匹配.group(1) if 股票匹配 else '600519'
    摘要 = {'股票代码':股票代码,'数据行数':0,'买入次数':0,'卖出次数':0,'胜率':0,'最终现金':20000000,'总收益率':0,'耗时':0}
    if os.path.exists(摘要文件):
        with open(摘要文件, 'r', encoding='utf-8') as f:
            for line in f:
                if ':' in line:
                    k, v = line.split(':', 1)
                    k = k.strip(); v = v.strip().replace(',','')
                    if k == '胜率': 摘要['胜率'] = float(v.replace('%',''))
                    elif k == '最终现金': 摘要['最终现金'] = float(v)
                    elif k == '总收益率': 摘要['总收益率'] = float(v.replace('%',''))
                    elif k == '耗时': 摘要['耗时'] = float(v.replace('秒',''))
    结果 = {'交易明细': 交易明细, '持仓过程': 持仓过程, **摘要}
    结果['数据行数'] = len(持仓过程) if len(持仓过程) > 0 else 0
    结果['买入次数'] = len(交易明细[交易明细['类型']=='买入'])
    结果['卖出次数'] = len(交易明细[交易明细['类型']=='卖出'])
    原始数据 = _加载数据(结果['股票代码'])
    路径 = 生成报告(结果, 原始数据)
    if 路径:
        print('已生成最新有效回测的 K 线回放页面')
