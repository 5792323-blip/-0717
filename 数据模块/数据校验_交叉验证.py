#!/usr/bin/env python3
# 数据校验_交叉验证.py
# 功能: 用 AKShare 免费接口交叉验证本地复权数据(不复权/前复权/后复权)是否准确
#
# 用法:
#   python 数据模块/数据校验_交叉验证.py                    # 默认抽样验证4只股票
#   python 数据模块/数据校验_交叉验证.py --codes 600519 000001
#   python 数据模块/数据校验_交叉验证.py --dates 2020-01-02 2024-12-02 2026-07-03
#
# 验证内容:
#   1. 不复权数据   : 本地日线聚合 vs AKShare 不复权
#   2. 前复权数据   : 本地前复权    vs AKShare qfq
#   3. 后复权推算   : 用本地 adj_factor 推算后复权 vs AKShare hfq
#                    (本地pkl未存后复权,但可验证 adj_factor 是否正确)
#
# 注意:
#   - 本地第一根60min跳过09:30集合竞价,开盘价用09:45 → 与AKShare日线开盘(09:30)有小差异
#     收盘价/最高/最低/成交量应一致
#   - AKShare有请求频率限制,每次调用间隔 sleep

import os, sys, time, argparse, warnings
import pandas as pd
import numpy as np
warnings.filterwarnings('ignore')

项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 项目根目录)

本地数据目录 = os.path.join(项目根目录, '数据模块', 'raw')
原始15min目录候选 = [
    os.path.expanduser('~/Desktop/A数据/parquet格式行情数据/行情数据更新到20260703/stock_15min'),
    os.path.expanduser('~/Desktop/A数据/parquet格式行情数据/行情数据更新至2026.7.10/stock_15min'),
]

# 默认抽样: 2只代表性股票(避免AKShare频率限制)
默认股票 = ['600519', '300750']
默认日期点 = ['2020-01-02', '2022-06-01', '2024-12-02', '2026-07-03']

# 误差容忍阈值(元/手): 考虑浮点精度和小数位差异
价格容差 = 0.05        # 价格差<0.05元视为一致
成交量容差比 = 0.01    # 成交量相对差<1%视为一致(含单位换算误差)
AK_SLEEP = 3.0         # AKShare请求间隔(秒),避免被限流


def 加载本地日线(股票代码):
    """加载本地60min数据并聚合为日线"""
    路径 = os.path.join(本地数据目录, f'{股票代码}_双价格合并.pkl')
    if not os.path.exists(路径):
        return None, None
    df = pd.read_pickle(路径)
    # 聚合为日线
    daily = df.groupby('日期').agg(
        前复权_开盘=('前复权_开盘', 'first'),
        前复权_最高=('前复权_最高', 'max'),
        前复权_最低=('前复权_最低', 'min'),
        前复权_收盘=('前复权_收盘', 'last'),
        不复权_开盘=('不复权_开盘', 'first'),
        不复权_最高=('不复权_最高', 'max'),
        不复权_最低=('不复权_最低', 'min'),
        不复权_收盘=('不复权_收盘', 'last'),
        成交量=('成交量', 'sum'),
        成交额=('成交额', 'sum'),
    ).reset_index()
    return daily, df


def 加载本地adj_factor(股票代码):
    """从原始15min parquet读取adj_factor序列(日线级别)"""
    ts_code = 股票代码 + ('.SH' if 股票代码.startswith(('6','5')) else '.SZ')
    for 目录 in 原始15min目录候选:
        for 后缀 in ['', '(1)']:
            路径 = os.path.join(目录, f'{ts_code}{后缀}.parquet')
            if os.path.exists(路径):
                df15 = pd.read_parquet(路径).reset_index()
                # 取每天的最后一个adj_factor
                adj = df15.groupby('trade_date')['adj_factor'].last().reset_index()
                adj['日期'] = adj['trade_date'].astype(str)
                return adj[['日期', 'adj_factor']]
    return None


def 获取akshare日线(股票代码, adjust, 开始='20200101', 结束='20260710'):
    """从AKShare获取日线数据"""
    import akshare as ak
    for 尝试 in range(3):
        try:
            df = ak.stock_zh_a_hist(
                symbol=股票代码, period='daily',
                start_date=开始, end_date=结束, adjust=adjust
            )
            return df
        except Exception as e:
            print(f'  (重试{尝试+1}/3) AKShare请求失败: {e}')
            time.sleep(3)
    return None


def 推算后复权(不复权值, adj当时, adj最早):
    """后复权 = 不复权 × adj当时 / adj最早 (以最早日期为基准)"""
    return 不复权值 * adj当时 / adj最早


def 对比一行(本地值, ak值, 容差=价格容差):
    """对比并返回差异"""
    if pd.isna(本地值) or pd.isna(ak值):
        return '缺失', np.nan
    diff = abs(本地值 - ak值)
    if diff <= 容差:
        return '一致', diff
    return '不一致', diff


def 验证单只股票(股票代码, 日期点列表):
    """验证一只股票的复权数据
    验证策略(避免复权基准差异):
      - 不复权价格: 直接对比绝对值
      - 成交量: 本地=股, AKShare=手, 本地/100后对比
      - 前复权/后复权: 对比"日收益率序列"(基准无关,最可靠)
    """
    print(f'\n{"="*70}')
    print(f'验证股票: {股票代码}')
    print(f'{"="*70}')

    # 1. 加载本地数据
    本地日线, _ = 加载本地日线(股票代码)
    本地adj = 加载本地adj_factor(股票代码)
    if 本地日线 is None:
        print(f'  ❌ 本地数据不存在')
        return None
    print(f'  本地数据: {len(本地日线)}个交易日  {本地日线["日期"].min()} ~ {本地日线["日期"].max()}')
    if 本地adj is not None:
        print(f'  adj_factor: {len(本地adj)}条  最早={本地adj["adj_factor"].iloc[0]:.4f}  最新={本地adj["adj_factor"].iloc[-1]:.4f}')

    # 2. 拉取AKShare三种复权数据(间隔sleep避免限流)
    print(f'  拉取AKShare数据中(间隔{AK_SLEEP}秒)...')
    ak_不复权 = 获取akshare日线(股票代码, '')
    time.sleep(AK_SLEEP)
    ak_qfq = 获取akshare日线(股票代码, 'qfq')
    time.sleep(AK_SLEEP)
    ak_hfq = 获取akshare日线(股票代码, 'hfq')
    time.sleep(AK_SLEEP)

    if ak_不复权 is None or ak_qfq is None or ak_hfq is None:
        print(f'  ❌ AKShare数据获取失败(可能被限流,稍后重试)')
        return None

    for df in [ak_不复权, ak_qfq, ak_hfq]:
        df['日期'] = df['日期'].astype(str)

    # 3. 不复权价格对比(直接对比绝对值)
    print(f'\n  --- [验证1] 不复权价格对比 ---')
    print(f'  {"日期":<12}{"指标":<6}{"本地":>12}{"AKShare":>12}{"状态":>6}')
    结果行 = []
    for 日期 in 日期点列表:
        本地行 = 本地日线[本地日线['日期'] == 日期]
        ak行 = ak_不复权[ak_不复权['日期'] == 日期]
        if 本地行.empty or ak行.empty:
            print(f'  {日期}: 数据缺失')
            continue
        本地 = 本地行.iloc[0]
        ak = ak行.iloc[0]
        for 指标 in ['收盘', '最高', '最低']:
            本地列 = f'不复权_{指标}'
            状态, diff = 对比一行(本地[本地列], ak[指标])
            print(f'  {日期:<12}{指标:<6}{本地[本地列]:>12.2f}{ak[指标]:>12.2f}{状态:>6}')
            结果行.append({'股票': 股票代码, '日期': 日期, '类别': '不复权', '指标': 指标,
                          '本地值': 本地[本地列], 'AK值': ak[指标], '状态': 状态, '差异': diff})

    # 4. 成交量对比(本地股 → 转手, 1手=100股)
    print(f'\n  --- [验证2] 成交量对比(本地股→手) ---')
    print(f'  {"日期":<12}{"本地(手)":>14}{"AKShare(手)":>14}{"相对差%":>10}{"状态":>6}')
    for 日期 in 日期点列表:
        本地行 = 本地日线[本地日线['日期'] == 日期]
        ak行 = ak_不复权[ak_不复权['日期'] == 日期]
        if 本地行.empty or ak行.empty:
            continue
        本地手 = 本地行.iloc[0]['成交量'] / 100.0
        ak手 = ak行.iloc[0]['成交量']
        if ak手 > 0:
            rel_diff = abs(本地手 - ak手) / ak手
            状态 = '一致' if rel_diff <= 成交量容差比 else '不一致'
        else:
            状态 = '缺失'
            rel_diff = np.nan
        print(f'  {日期:<12}{本地手:>14.0f}{ak手:>14.0f}{rel_diff*100:>9.3f}%{状态:>6}')
        结果行.append({'股票': 股票代码, '日期': 日期, '类别': '成交量', '指标': '成交量',
                      '本地值': 本地手, 'AK值': ak手, '状态': 状态, '差异': rel_diff})

    # 5. 前复权日收益率对比(基准无关)
    print(f'\n  --- [验证3] 前复权日收益率对比(基准无关,最可靠) ---')
    本地qfq_ret = 本地日线['前复权_收盘'].pct_change()
    akqfq_ret = ak_qfq['收盘'].pct_change()
    # 对齐日期
    本地ret_df = pd.DataFrame({'日期': 本地日线['日期'], '本地前复权收益率': 本地qfq_ret})
    akret_df = pd.DataFrame({'日期': ak_qfq['日期'], 'AK前复权收益率': akqfq_ret})
    merged = 本地ret_df.merge(akret_df, on='日期', how='inner')
    merged = merged.dropna()
    print(f'  {"日期":<12}{"本地收益率%":>14}{"AKShare收益率%":>16}{"差值%":>10}{"状态":>6}')
    样本数 = 0
    一致数 = 0
    # 取验证日期点附近各显示1个,以及抽样统计
    显示日期 = set(日期点列表)
    for _, row in merged.iterrows():
        diff = abs(row['本地前复权收益率'] - row['AK前复权收益率'])
        状态 = '一致' if diff < 0.0001 else '不一致'  # 0.01%以内
        样本数 += 1
        if 状态 == '一致':
            一致数 += 1
        if row['日期'] in 显示日期:
            print(f'  {row["日期"]:<12}{row["本地前复权收益率"]*100:>13.4f}%{row["AK前复权收益率"]*100:>15.4f}%{diff*100:>9.5f}%{状态:>6}')
    if 样本数 > 0:
        print(f'  → 前复权日收益率一致率: {一致数}/{样本数} ({一致数/样本数*100:.1f}%)')
        结果行.append({'股票': 股票代码, '日期': '全样本', '类别': '前复权收益率', '指标': '一致率',
                      '本地值': 一致数/样本数, 'AK值': 样本数, '状态': '一致' if 一致数/样本数>=0.95 else '不一致',
                      '差异': 1-一致数/样本数})

    # 6. 后复权日收益率对比(本地adj_factor推算后复权)
    if 本地adj is not None:
        print(f'\n  --- [验证4] 后复权日收益率对比(本地adj推算 vs AKShare hfq) ---')
        本地日线_adj = 本地日线.merge(本地adj, on='日期', how='left')
        adj最早 = 本地adj['adj_factor'].iloc[0]
        本地日线_adj['后复权_收盘'] = 推算后复权(本地日线_adj['不复权_收盘'], 本地日线_adj['adj_factor'], adj最早)
        本地hfq_ret = 本地日线_adj['后复权_收盘'].pct_change()
        akhfq_ret = ak_hfq['收盘'].pct_change()
        本地ret_df = pd.DataFrame({'日期': 本地日线_adj['日期'], '本地后复权收益率': 本地hfq_ret})
        akret_df = pd.DataFrame({'日期': ak_hfq['日期'], 'AK后复权收益率': akhfq_ret})
        merged = 本地ret_df.merge(akret_df, on='日期', how='inner').dropna()
        print(f'  {"日期":<12}{"本地收益率%":>14}{"AKShare收益率%":>16}{"差值%":>10}{"状态":>6}')
        样本数 = 0
        一致数 = 0
        for _, row in merged.iterrows():
            diff = abs(row['本地后复权收益率'] - row['AK后复权收益率'])
            状态 = '一致' if diff < 0.0001 else '不一致'
            样本数 += 1
            if 状态 == '一致':
                一致数 += 1
            if row['日期'] in 显示日期:
                print(f'  {row["日期"]:<12}{row["本地后复权收益率"]*100:>13.4f}%{row["AK后复权收益率"]*100:>15.4f}%{diff*100:>9.5f}%{状态:>6}')
        if 样本数 > 0:
            print(f'  → 后复权日收益率一致率: {一致数}/{样本数} ({一致数/样本数*100:.1f}%)')
            结果行.append({'股票': 股票代码, '日期': '全样本', '类别': '后复权收益率', '指标': '一致率',
                          '本地值': 一致数/样本数, 'AK值': 样本数, '状态': '一致' if 一致数/样本数>=0.95 else '不一致',
                          '差异': 1-一致数/样本数})

    return pd.DataFrame(结果行)


def 主程序(股票列表, 日期列表):
    print('\n' + '='*70)
    print('数据校验 — AKShare 交叉验证')
    print('='*70)
    print(f'验证股票: {股票列表}')
    print(f'验证日期: {日期列表}')
    print(f'价格容差: {价格容差}元  成交量容差: {成交量容差比*100}%')

    全部结果 = []
    for 股票 in 股票列表:
        结果 = 验证单只股票(股票, 日期列表)
        if 结果 is not None:
            全部结果.append(结果)

    if not 全部结果:
        print('\n❌ 无有效验证结果')
        return

    汇总 = pd.concat(全部结果, ignore_index=True)
    print('\n\n' + '='*70)
    print('验证汇总报告')
    print('='*70)

    # 按类别统计一致率
    for 类别 in ['不复权', '成交量', '前复权收益率', '后复权收益率']:
        子集 = 汇总[汇总['类别'] == 类别]
        if len(子集) == 0:
            continue
        一致 = (子集['状态'] == '一致').sum()
        print(f'{类别:<12}: {一致}/{len(子集)} 一致 ({一致/len(子集)*100:.1f}%)')

    # 显示不一致项
    不一致 = 汇总[汇总['状态'] == '不一致']
    if len(不一致) > 0:
        print(f'\n不一致项明细:')
        显示列 = [c for c in ['股票','日期','类别','指标','本地值','AK值','差异'] if c in 不一致.columns]
        print(不一致[显示列].to_string(index=False))

    # 保存结果
    输出路径 = os.path.join(项目根目录, '数据模块', '校验结果_最新.csv')
    汇总.to_csv(输出路径, index=False, encoding='utf-8-sig')
    print(f'\n详细结果已保存: {输出路径}')

    # 最终结论: 以不复权价格 + 复权收益率一致率为准
    不复权子集 = 汇总[汇总['类别'] == '不复权']
    不复权一致率 = (不复权子集['状态']=='一致').sum()/len(不复权子集) if len(不复权子集)>0 else 0
    收益率子集 = 汇总[汇总['类别'].isin(['前复权收益率','后复权收益率'])]
    收益率一致率 = (收益率子集['状态']=='一致').sum()/len(收益率子集) if len(收益率子集)>0 else 0

    print('\n' + '='*70)
    if 不复权一致率 >= 0.9 and 收益率一致率 >= 0.95:
        print(f'✅ 结论: 数据真实可靠')
        print(f'   不复权价格一致率: {不复权一致率*100:.1f}%')
        print(f'   复权收益率一致率: {收益率一致率*100:.1f}% (基准无关)')
        print(f'   (绝对值因复权基准不同会有差异,但收益率序列一致即证明adj_factor正确)')
    elif 不复权一致率 >= 0.9:
        print(f'⚠️  结论: 原始价格真实,但复权体系需进一步核对')
        print(f'   不复权价格一致率: {不复权一致率*100:.1f}%')
        print(f'   复权收益率一致率: {收益率一致率*100:.1f}%')
    else:
        print(f'❌ 结论: 原始价格存在差异,建议排查数据源 (不复权一致率 {不复权一致率*100:.1f}%)')
    print('='*70)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='用AKShare交叉验证本地复权数据')
    parser.add_argument('--codes', nargs='+', default=默认股票, help='股票代码列表')
    parser.add_argument('--dates', nargs='+', default=默认日期点, help='验证日期点(YYYY-MM-DD)')
    args = parser.parse_args()
    主程序(args.codes, args.dates)
