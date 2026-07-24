# backtest_engine.py — 单股逐K线回测引擎
# 功能: 加载一只股票的数据，逐根K线运行回测，输出结果
#
# 用法:
#   python 回测引擎/backtest_engine.py

import os
import sys
import pandas as pd
import numpy as np
import yaml
from datetime import datetime

# 添加项目根目录到路径
项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 项目根目录)


def _计算基准曲线(数据, 初始资金):
    """按回测日期生成个股买入持有和HS300归一化基准。"""
    股票首价 = float(数据['不复权_收盘'].iloc[0])
    个股曲线 = []
    hs曲线 = []
    hs路径 = os.path.join(项目根目录, '数据模块', '大盘数据', 'hs300_日K线.pkl')
    hs数据 = pd.read_pickle(hs路径) if os.path.exists(hs路径) else pd.DataFrame()
    if len(hs数据) > 0:
        hs数据['date'] = hs数据['date'].astype(str)
        hs首日 = str(数据['日期'].iloc[0])[:10]
        hs候选 = hs数据[hs数据['date'] >= hs首日]
        hs首价 = float(hs候选['close'].iloc[0]) if len(hs候选) else 0
        hs映射 = hs数据.set_index('date')['close'].to_dict()
    else:
        hs首价, hs映射 = 0, {}
    最近HS = hs首价
    for idx, row in 数据.iterrows():
        日期 = str(row['日期'])[:10]
        个股曲线.append(round(初始资金 * float(row['不复权_收盘']) / 股票首价, 2))
        if 日期 in hs映射:
            最近HS = float(hs映射[日期])
        hs曲线.append(round(初始资金 * 最近HS / hs首价, 2) if hs首价 else None)
    return 个股曲线, hs曲线


def 准备回测数据(股票代码, 开始日期=None, 结束日期=None, 配置目录=None):
    """统一准备单股和多股会话使用的指标数据。"""
    from 数据模块.股票加载器 import 加载股票
    from 策略引擎.rsi_source import 准备RSI指标
    from 策略引擎.atr import 计算ATR

    数据 = 加载股票(股票代码, "双价格合并")
    if 数据 is None:
        return None, None, None, None

    配置目录 = os.path.abspath(
        配置目录 or os.path.join(项目根目录, '1_策略配置')
    )
    with open(os.path.join(配置目录, '参数配置.yaml'), encoding='utf-8') as 配置文件:
        参数配置 = yaml.safe_load(配置文件) or {}
    技术参数 = 参数配置.get('技术指标参数', {})
    数据 = 准备RSI指标(
        数据,
        价格源=技术参数.get('RSI价格源', 'close'),
        RSI周期=技术参数.get('RSI周期', 14),
        均线周期=技术参数.get('RSI均线周期', 20),
    )
    数据 = 数据.copy()
    数据['ATR_14'] = 计算ATR(
        数据['前复权_最高'], 数据['前复权_最低'], 数据['前复权_收盘'],
        周期=int(技术参数.get('ATR周期', 14)),
    )

    if 开始日期:
        数据 = 数据[数据['日期'] >= 开始日期]
    if 结束日期:
        数据 = 数据[数据['日期'] <= 结束日期]
    if len(数据) < 100:
        return None, 配置目录, 参数配置, 技术参数

    if '成交额' in 数据.columns:
        日期键 = 数据['日期'].astype(str).str[:10]
        日成交额 = 数据.groupby(日期键)['成交额'].sum()
        上一日成交额 = 日成交额.shift(1)
        上一日成交额均值20 = 日成交额.shift(1).rolling(20, min_periods=5).mean()
        数据 = 数据.copy()
        数据['_上一交易日成交额'] = 日期键.map(上一日成交额)
        数据['_上一交易日成交额比20日均值'] = 日期键.map(
            上一日成交额 / 上一日成交额均值20
        )
    return 数据, 配置目录, 参数配置, 技术参数


def 跑回测(股票代码="600519", 开始日期=None, 结束日期=None,
          初始资金=20000000, 输出目录=None, 运行参数=None, 配置目录=None,
          静默=False):
    """
    跑单只股票的回测
    
    传入:
        股票代码   - 如 "600519"
        开始日期   - 如 "2020-01-01"，None=全部
        结束日期   - 如 "2024-12-31"，None=全部
        初始资金   - 回测初始资金，默认2000万
        输出目录   - 结果输出目录，默认自动创建
    
    传出:
        字典: {"交易明细": DataFrame, "持仓过程": DataFrame, "最终现金": 金额, ...}
    """
    
    from 策略引擎.规则执行器 import 规则执行器
    
    def 输出(*args, **kwargs):
        if not 静默:
            print(*args, **kwargs)

    输出(f"\n{'='*50}")
    输出(f"回测开始: {股票代码}")
    输出(f"{'='*50}")
    
    # 1. 加载并按同一入口准备指标数据
    数据, 配置目录, _参数配置, _技术参数 = 准备回测数据(
        股票代码, 开始日期, 结束日期, 配置目录
    )
    if 数据 is None:
        输出(f"❌ 无法加载 {股票代码} 的数据，或日期范围内数据不足100行")
        return None
    
    输出(f"   股票: {股票代码}  |  数据: {len(数据)} 行")
    输出(f"   时间: {数据['日期'].iloc[0]} ~ {数据['日期'].iloc[-1]}")
    输出(f"   资金: {初始资金:,}")
    
    # 3. 初始化规则执行器
    执行器 = 规则执行器(
        配置目录, 运行参数=运行参数, 股票代码=股票代码
    )
    执行器.当前现金 = 初始资金
    
    # 4. 逐K线运行
    输出(f"\n   正在运行回测 (共{len(数据)}根K线)...")
    开始时间 = datetime.now()
    
    上一根RSI = 50  # 初始值
    上一根最低价RSI = 50
    for i in range(len(数据)):
        行 = 数据.iloc[i]
        # 使用普通字典承载当前K线，避免个别数据行/列索引异常时，
        # pandas Series 对新增内部字段走到异常的 loc 回退路径。
        # 规则执行器只依赖下标访问和 get()，字典与 Series 语义一致。
        行_copy = 行.to_dict()
        行_copy['_上一根RSI'] = 上一根RSI
        行_copy['_上一根最低价RSI'] = 上一根最低价RSI
        执行器.每根K线处理(行_copy, i)
        上一根RSI = 行.get('RSI_14', 50)  # 更新供下次使用
        上一根最低价RSI = 行.get('RSI_最低价', 上一根RSI)
        
        # 打印进度 (每10%)
        if (i+1) % max(1, len(数据)//10) == 0:
            输出(f"   进度: {i+1}/{len(数据)} ({100*(i+1)//len(数据)}%)")
    
    耗时 = (datetime.now() - 开始时间).total_seconds()
    
    # 5. 获取结果
    结果 = 执行器.获取结果(数据.iloc[-1])
    结果['股票代码'] = 股票代码
    结果['初始资金'] = 初始资金
    结果['运行参数'] = 运行参数 or {}
    结果['RSI价格源'] = _技术参数.get('RSI价格源', 'close')
    结果['买入时机模式'] = _参数配置.get('买入参数', {}).get(
        '买入时机模式', 'precomputed_stop_entry'
    )
    from 时序审计.trade_timing_audit import 审计回测
    结果['时序审计'] = 审计回测(结果['交易明细'], 结果['买入时机模式'])
    结果['数据行数'] = len(数据)
    结果['原始K线数据'] = 数据
    结果['耗时'] = 耗时
    结果['基准_个股买入持有'], 结果['基准_HS300'] = _计算基准曲线(数据, 初始资金)
    结果['配置快照'] = {}
    for 文件名 in ['买入信号配置.yaml', '卖出规则配置.yaml', '仓位配置.yaml', '参数配置.yaml',
                   '过滤因子配置.yaml', '因子配置.yaml', '核心模块配置.yaml',
                   '模块开关配置.yaml']:
        with open(os.path.join(配置目录, 文件名), encoding='utf-8') as 配置文件:
            结果['配置快照'][文件名] = yaml.safe_load(配置文件)
    
    # 6. 计算绩效
    总交易 = 结果['交易明细']
    买入列表 = 总交易[总交易['类型'] == '买入'] if len(总交易) > 0 else pd.DataFrame()
    卖出列表 = 总交易[总交易['类型'] == '卖出'] if len(总交易) > 0 else pd.DataFrame()
    
    结果['买入次数'] = len(买入列表)
    结果['卖出次数'] = len(卖出列表)
    
    if len(卖出列表) > 0 and '盈亏比例' in 卖出列表.columns:
        盈利次数 = (卖出列表['盈亏比例'] > 0).sum()
        结果['胜率'] = 盈利次数 / max(len(卖出列表), 1) * 100
        结果['平均盈亏'] = 卖出列表['盈亏比例'].mean() * 100
    else:
        结果['胜率'] = 0
        结果['平均盈亏'] = 0
    
    结果['总收益率'] = (结果['最终权益'] - 初始资金) / 初始资金 * 100
    权益序列 = pd.to_numeric(结果['持仓过程'].get('权益', pd.Series(dtype=float)), errors='coerce').dropna()
    if len(权益序列) > 0:
        结果['最大回撤'] = float(((权益序列.cummax() - 权益序列) /权益序列.cummax()).max() * 100)
    else:
        结果['最大回撤'] = 0.0
    盈亏 = pd.to_numeric(卖出列表.get('盈亏比例', pd.Series(dtype=float)), errors='coerce').dropna()
    盈利 = 盈亏[盈亏 > 0]
    亏损 =盈亏[盈亏 < 0]
    结果['平均盈利'] = float(盈利.mean() * 100) if len(盈利) else 0.0
    结果['平均亏损'] = float(亏损.mean() * 100) if len(亏损) else 0.0
    结果['盈亏比'] = float(盈利.sum() / abs(亏损.sum())) if len(亏损) and 亏损.sum() else None
    # Profit Factor 应使用金额，而不是百分比求和。
    if len(卖出列表) and {'卖出价', '盈亏比例'}.issubset(卖出列表.columns):
        金额盈亏 = pd.to_numeric(卖出列表['盈亏比例'], errors='coerce') * pd.to_numeric(
            卖出列表.get('仓位', pd.Series(index=卖出列表.index, dtype=float)), errors='coerce'
        )
        金额盈亏 = 金额盈亏.dropna()
        总盈利金额 = 金额盈亏[金额盈亏 > 0].sum()
        总亏损金额 = 金额盈亏[金额盈亏 < 0].sum()
        结果['Profit Factor'] = float(总盈利金额 / abs(总亏损金额)) if 总亏损金额 else None
    else:
        结果['Profit Factor'] = None
    
    # 7. 打印摘要
    输出(f"\n   ✅ 回测完成 ({耗时:.1f}秒)")
    输出(f"   {'='*35}")
    输出(f"   交易: {结果['买入次数']}买 / {结果['卖出次数']}卖")
    输出(f"   胜率: {结果['胜率']:.1f}%")
    输出(f"   平均盈亏: {结果['平均盈亏']:+.2f}%")
    输出(f"   最终现金: {结果['最终现金']:,.0f}")
    输出(f"   期末持仓市值: {结果['期末持仓市值']:,.0f}")
    输出(f"   最终权益: {结果['最终权益']:,.0f}")
    输出(f"   总收益率: {结果['总收益率']:+.2f}%")
    输出(f"   最大回撤: {结果['最大回撤']:.2f}%")
    输出(f"   剩余持仓: {结果['剩余持仓']}")
    
    return 结果


def 保存结果(结果, 输出目录=None):
    """保存回测结果到文件"""
    if 结果 is None:
        return None
    
    股票代码 = 结果.get('股票代码', 'unknown')
    时间戳 = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if 输出目录 is None:
        输出目录 = os.path.join(项目根目录, '10_实验记录', f'{时间戳}_{股票代码}')
    
    os.makedirs(输出目录, exist_ok=True)

    # 将本次回测使用的完整配置单独落盘，便于页面解释和一键人工回退。
    配置快照目录 = os.path.join(输出目录, '配置快照')
    os.makedirs(配置快照目录, exist_ok=True)
    配置快照 = 结果.get('配置快照', {})
    for 文件名, 内容 in 配置快照.items():
        with open(os.path.join(配置快照目录, 文件名), 'w', encoding='utf-8') as 配置文件:
            yaml.safe_dump(内容, 配置文件, allow_unicode=True, sort_keys=False)
    
    # 保存交易明细
    if len(结果['交易明细']) > 0:
        结果['交易明细'].to_csv(f'{输出目录}/交易明细.csv', index=False, encoding='utf-8-sig')
    
    # 保存持仓过程
    if len(结果['持仓过程']) > 0:
        结果['持仓过程'].to_csv(f'{输出目录}/持仓过程.csv', index=False, encoding='utf-8-sig')
    
    # 保存摘要
    with open(f'{输出目录}/回测摘要.txt', 'w', encoding='utf-8') as f:
        f.write(f"股票代码: {股票代码}\n")
        f.write(f"数据行数: {结果.get('数据行数', 0)}\n")
        f.write(f"交易次数: {结果.get('买入次数', 0)}买 / {结果.get('卖出次数', 0)}卖\n")
        f.write(f"胜率: {结果.get('胜率', 0):.1f}%\n")
        f.write(f"平均盈亏: {结果.get('平均盈亏', 0):+.2f}%\n")
        f.write(f"最终现金: {结果.get('最终现金', 0):,.0f}\n")
        f.write(f"期末持仓市值: {结果.get('期末持仓市值', 0):,.0f}\n")
        f.write(f"最终权益: {结果.get('最终权益', 0):,.0f}\n")
        f.write(f"总收益率: {结果.get('总收益率', 0):+.2f}%\n")
        f.write(f"最大回撤: {结果.get('最大回撤', 0):.2f}%\n")
        f.write(f"平均盈利: {结果.get('平均盈利', 0):+.2f}%\n")
        f.write(f"平均亏损: {结果.get('平均亏损', 0):+.2f}%\n")
        f.write(f"盈亏比: {结果.get('盈亏比', 0) if 结果.get('盈亏比') is not None else '--'}\n")
        f.write(f"初始资金: {结果.get('初始资金', 0):,.0f}\n")
        f.write(f"耗时: {结果.get('耗时', 0):.1f}秒\n")
    
    print(f"\n   结果已保存: {输出目录}")
    # 自动生成HTML报告
    try:
        from 回测引擎.report_generator import 生成报告
        结果['股票代码'] = 结果.get('股票代码', 'unknown')
        生成报告(结果, 结果.get('原始K线数据'))
    except Exception as e:
        print(f'   ⚠️ HTML报告生成失败: {e}')
    return 输出目录


if __name__ == "__main__":
    结果 = 跑回测("600519", "2020-01-01", "2024-12-31")
    if 结果:
        保存结果(结果)
