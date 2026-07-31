# 规则执行器.py — 读取配置，执行买卖规则 (核心调度器)
# 功能: 每根K线调用一次，检查买入/卖出/仓位，执行交易
# 这是整个策略的大脑
#
# 用法:
#   from 策略引擎.规则执行器 import 规则执行器
#   执行器 = 规则执行器(配置目录)
#   执行器.每根K线处理(...)

import os
import yaml
import pandas as pd
import numpy as np
from 策略引擎.反推因子 import 智能反推
from 模块系统 import 模块开关管理器
from 买入执行模块.entry_timing import (
    CLOSE_NEXT_OPEN, LEGACY_SAME_BAR, SAME_BAR_ENTRY, STRICT_PRECOMPUTED, TB_REPLAY,
    哨兵价可执行, 是严格模式, 规范化模式, 使用收盘确认, 允许旧版本根回填,
)
from 成交模型.buy_fill_model import 计算买入成交, 计算回撤买入成交
from 买入执行模块.sentinel_trigger import 形成候选, 评估触发
from 买入执行模块.rsi_reverse_price import (
    计算 as 计算RSI反推价,
    计算Wilder上涨反推价,
    计算WilderRSI,
)
from 策略引擎.交易账户 import 单股账户


class 规则执行器:
    """
    规则执行器
    
    流程:
    每根K线:
      ① 更新指标 (RSI/RSI_MA/ATR等)
      ② 检查买入信号 (遍历买入规则)
      ③ 信号过滤 (质量评分/大盘状态/仓位限制)
      ④ 如果有信号 → 计算仓位 → 买入
      ⑤ 检查持仓的卖出条件
      ⑥ 记录本根K线的状态
    """
    
    @property
    def current_sentinel_price(self):
        return self.哨兵价当前

    @current_sentinel_price.setter
    def current_sentinel_price(self, value):
        self.哨兵价当前 = value

    @property
    def sentinel_tracking_enabled(self):
        return getattr(self, '哨兵价跟踪启用', False)

    @sentinel_tracking_enabled.setter
    def sentinel_tracking_enabled(self, value):
        self.哨兵价跟踪启用 = bool(value)

    @property
    def sentinel_consumed_price(self):
        return getattr(self, '哨兵价已消费价格', None)

    @sentinel_consumed_price.setter
    def sentinel_consumed_price(self, value):
        self.哨兵价已消费价格 = value

    @property
    def last_trade_sentinel_price(self):
        return getattr(self, '最近成交哨兵价', None)

    @last_trade_sentinel_price.setter
    def last_trade_sentinel_price(self, value):
        self.最近成交哨兵价 = value

    @property
    def sentinel_type(self):
        return self.哨兵价形成类型

    @sentinel_type.setter
    def sentinel_type(self, value):
        self.哨兵价形成类型 = value

    @property
    def 当前现金(self):
        if hasattr(self, '账户视图'):
            return self.账户视图.现金
        return getattr(self, '_当前现金', 0.0)

    @当前现金.setter
    def 当前现金(self, value):
        if hasattr(self, '账户视图'):
            self.账户视图.现金 = value
        else:
            self._当前现金 = float(value)

    @property
    def 当前持仓(self):
        if hasattr(self, '账户视图'):
            return self.账户视图.持仓
        return getattr(self, '_当前持仓', {})

    @当前持仓.setter
    def 当前持仓(self, value):
        if hasattr(self, '账户视图'):
            self.账户.持仓.clear()
            self.账户.持仓.update(dict(value or {}))
        else:
            self._当前持仓 = dict(value or {})

    def _账户已达到最大持仓数(self, 股票代码):
        if hasattr(self, '账户视图'):
            return self.账户视图.已达到最大持仓数(self.最大总持仓数)
        return (
            len(self.当前持仓) >= self.最大总持仓数
            and 股票代码 not in self.当前持仓
        )

    def _记录策略异常(self, 模块, error, 当前索引=None):
        """记录不应静默消失的策略计算异常，但不改变原有容错流程。"""
        message = str(error) or error.__class__.__name__
        row = {
            "模块": str(模块),
            "错误类型": error.__class__.__name__,
            "错误信息": message,
            "K线索引": 当前索引,
        }
        self.策略异常记录 = getattr(self, "策略异常记录", [])
        self.策略异常计数 = getattr(self, "策略异常计数", {})
        self.策略异常记录.append(row)
        self.策略异常计数[str(模块)] = self.策略异常计数.get(str(模块), 0) + 1
        if isinstance(getattr(self, "本根决策", None), dict):
            self.本根决策.setdefault("策略异常", []).append(row)

    def _计算账户结构性可用金额(self, 当前估值价):
        if hasattr(self, '账户视图'):
            return self.账户视图.计算结构性可用金额(
                当前估值价,
                self.最大单只比例,
                self.最大总仓位比例,
                self.现金底线比例,
            )
        当前持仓市值 = sum(
            p.get('股数', 0) * 当前估值价 for p in self.当前持仓.values()
        )
        当前权益 = self.当前现金 + 当前持仓市值
        现金可用金额 = max(0.0, self.当前现金 - 当前权益 * self.现金底线比例)
        单只仓位限制已关闭 = float(self.最大单只比例) <= 0
        单股上限金额 = 现金可用金额 if 单只仓位限制已关闭 else 当前权益 * self.最大单只比例
        总仓位限制已关闭 = float(self.最大总仓位比例) <= 0
        总仓位剩余 = (
            现金可用金额 if 总仓位限制已关闭
            else max(0.0, 当前权益 * self.最大总仓位比例 - 当前持仓市值)
        )
        return min(单股上限金额, 总仓位剩余, 现金可用金额), {
            "当前权益": 当前权益,
            "持仓市值": 当前持仓市值,
            "单只结构性上限": 单股上限金额,
            "单只仓位限制已关闭": 单只仓位限制已关闭,
            "总仓位剩余": 总仓位剩余,
            "总仓位限制已关闭": 总仓位限制已关闭,
            "现金可用金额": 现金可用金额,
        }

    def _记录账户审批(self, **row):
        if not getattr(self, '运行参数', {}).get('共享账户模式', False):
            return
        if hasattr(self, '账户视图'):
            if hasattr(self, '_组合优先级'):
                row.setdefault('组合优先级', list(self._组合优先级))
                row.setdefault('组合撮合规则', getattr(self, '_组合撮合规则', ''))
            if row.get('结果') == '组合层拦截':
                row.setdefault('拒绝分类', self._拒绝分类(row))
                row.setdefault('详细原因', self._拒绝详细原因(row))
            self.账户视图.记录审批(**row)

    @staticmethod
    def _拒绝分类(row):
        text = str(row.get('原因', '') or '')
        limits = row.get('账户限制') or {}
        minimum = row.get('最低一手含费用')
        def numeric(value, default=float('inf')):
            try:
                return float(value)
            except (TypeError, ValueError):
                return default
        if text == '资金不足一手' and isinstance(minimum, (int, float)):
            if numeric(row.get('当前现金'), 0.0) < minimum:
                return '现金余额不足'
            if numeric(limits.get('买入流动性上限')) < minimum:
                return '买入流动性限制'
            if numeric(row.get('买入金额上限')) < minimum:
                return '策略或单只仓位上限'
            if numeric(limits.get('总仓位剩余')) < minimum:
                return '组合总仓位上限'
            return '最低交易单位限制'
        if '最大持仓' in text:
            return '最大持仓数量限制'
        if '流动性' in text or '成交额' in text:
            return '买入流动性限制'
        if '部分成交' in text:
            return '禁止部分成交设置'
        if '现金' in text:
            return '现金或现金保留限制'
        if '仓位' in text or '一手' in text:
            return '账户结构额度限制'
        return '交易条件限制'

    @staticmethod
    def _拒绝详细原因(row):
        limits = row.get('账户限制') or {}
        parts = []
        for label, key in (
            ('现金可用', '现金可用金额'), ('单只剩余', '单只结构性上限'),
            ('总仓位剩余', '总仓位剩余'), ('流动性上限', '买入流动性上限'),
        ):
            value = limits.get(key)
            if isinstance(value, (int, float)):
                parts.append(f'{label}{value:,.2f}元')
        minimum = row.get('最低一手含费用')
        if isinstance(minimum, (int, float)):
            parts.insert(0, f'最低一手含费用{minimum:,.2f}元')
        upper = row.get('买入金额上限')
        if isinstance(upper, (int, float)):
            parts.append(f'本次买入上限{upper:,.2f}元')
        cash = row.get('当前现金')
        if isinstance(cash, (int, float)):
            parts.append(f'当前现金{cash:,.2f}元')
        return f"{row.get('原因', '未说明')}；" + '，'.join(parts) if parts else str(row.get('原因', '未说明'))

    def __init__(self, 配置目录, 运行参数=None, 账户=None, 股票代码="600519"):
        """
        初始化规则执行器

        传入:
            配置目录 - 1_策略配置/ 目录的路径
        """

        self.配置目录 = 配置目录
        self.运行参数 = 运行参数 or {}
        self.模块开关 = 模块开关管理器(配置目录)
        self.核心模块配置 = self._加载yaml('核心模块配置.yaml')
        self.核心模块 = self.核心模块配置.get('核心模块', {})
        self.交易记录器 = __import__('策略引擎.交易记录器', fromlist=['交易记录器']).交易记录器()
        
        # 加载配置
        self.买入配置 = self._加载yaml('买入信号配置.yaml')
        self.卖出配置 = self._加载yaml('卖出规则配置.yaml')
        self.仓位配置 = self._加载yaml('仓位配置.yaml')
        self.参数配置 = self._加载yaml('参数配置.yaml')
        
        # 账户只承载真实现金和持仓；策略、成交、费用与网格仍由本执行器
        # 唯一计算。多股模式为每只股票注入同一共享账户的独立股票视图。
        初始资金 = self.仓位配置.get('基准仓位', {}).get('初始资金', 20000000)
        self.账户 = 账户 or 单股账户(初始资金)
        self.账户视图 = self.账户.股票视图(股票代码)
        self.已买入K线数 = 0
        # LightGBM预测器
        try:
            from 策略引擎.predictor import LightGBM预测器
            self.预测器 = LightGBM预测器()
            self.预测器调用次数 = 0
            self.预测器调整次数 = 0
            self.预测器跳过次数 = 0
        except:
            self.预测器 = None
        import collections
        self.RSI_MA历史 = collections.deque(maxlen=20)
        
        # 从配置中提取参数
        基准 = self.仓位配置.get('基准仓位', {})
        self.基础单只金额 = 基准.get('基础单只金额', 200000)
        self.最大单只比例 = 基准.get('最大单只比例', 0.10)
        self.最大总持仓数 = 基准.get('最大总持仓数', 200)
        self.最大总仓位比例 = 基准.get('最大总仓位比例', 0.98)
        self.现金底线比例 = float(基准.get('现金底线', 0.20))
        self.单股全仓模式 = bool(self.运行参数.get('单股全仓模式', False))
        self.流动性上限比例 = self.运行参数.get('流动性上限比例')

        成本 = self.参数配置.get('交易成本', {})
        self.滑点 = float(成本.get('滑点', 0.001))
        self.佣金率 = float(成本.get('佣金', 0.00025))
        self.印花税率 = float(成本.get('印花税', 0.001))
        self.买入溢价 = float(成本.get('买入溢价', 1 + self.滑点))
        self.过户费率 = float(成本.get('过户费', 0.00001))
        技术参数 = self.参数配置.get('技术指标参数', {})
        买入参数 = self.参数配置.get('买入参数', {})
        卖出参数 = self.参数配置.get('卖出参数', {})
        self.RSI价格源 = str(技术参数.get('RSI价格源', 'close'))
        self.信号过期K线数 = int(技术参数.get('信号过期K线数', 72))
        self.哨兵价本根形成立即买入 = bool(技术参数.get('哨兵价本根形成立即买入', True))
        if '本根形成立即成交' in self.核心模块:
            self.哨兵价本根形成立即买入 = bool(self.核心模块['本根形成立即成交'].get('启用', False))
        self.哨兵价本根形成立即买入 = self._核心模块启用(
            '本根形成立即成交', self.哨兵价本根形成立即买入
        )
        self.涨跌停比例 = float(买入参数.get('涨跌停比例', 0.10))
        self.涨停不买 = bool(买入参数.get('涨停不买', True))
        self.首次开仓时机模式 = 规范化模式(
            买入参数.get(
                '首次开仓时机模式',
                买入参数.get('买入时机模式', STRICT_PRECOMPUTED),
            )
        )
        self.网格加仓时机模式 = 规范化模式(
            买入参数.get('网格加仓时机模式', STRICT_PRECOMPUTED)
        )
        # 旧代码路径继续读取这个字段；它现在明确代表首次开仓时机。
        self.买入时机模式 = self.首次开仓时机模式
        self.待次根开盘买入 = None
        self.卖出时机模式 = str(
            self.运行参数.get(
                '卖出时机模式', 卖出参数.get('卖出时机模式', 'intrabar_stop')
            )
        )
        if self.卖出时机模式 not in ('intrabar_stop', 'next_bar_open'):
            self.卖出时机模式 = 'intrabar_stop'
        self.待次根开盘卖出 = {}
        # 同一根K线只允许一次普通买入；跨K线可继续增持同一股票。
        self._本根已买入股票 = set()
        
        self.信号质量对照 = self.仓位配置.get('信号质量调整', {})
        self.大盘系数对照 = self.仓位配置.get('大盘系数调整', {})
        
        # 市场状态跟踪（供信号质量评分使用）
        self.大盘状态 = "震荡模式"
        self.有底背离 = False
        self.有顶背离 = False
        self.价格序列 = []
        self.RSI序列 = []
        self.上一根_最高价 = None
        self.上一根_最低价 = None
        self.上一根_不复权收盘 = None
        self.上一根_ATR = None
        self.上一根_RSI_MA = None
        self._上上根_RSI_MA = None
        self.本根决策 = {}
        self.策略异常记录 = []
        self.策略异常计数 = {}

        # 独立卖出保护：只影响配置中声明的卖出规则（默认仅 ATR 跟踪）。
        self.RSI阈值守仓配置 = next(
            (item for item in self.卖出配置.get('卖出条件列表', [])
             if item.get('英文标识') == 'rsi_threshold_hold'),
            {},
        )
        self.RSI阈值守仓启用 = self.模块开关.是否启用(
            '卖出规则', 'rsi_threshold_hold', self.RSI阈值守仓配置.get('启用', False)
        )
        self.RSI阈值守仓状态 = {}

        # 哨兵价追踪变量（独立于买入卖出，持续跟踪）
        self.哨兵价当前 = None
        self.RSI反推价当前 = None
        self.上一根突破基准价当前 = None
        self.最终买入触发价当前 = None
        self.哨兵价已形成 = False
        self.哨兵价跟踪启用 = False
        self.哨兵价可执行 = False
        self.哨兵价已消费价格 = None
        self.最近成交哨兵价 = None
        self.哨兵价形成类型 = None        
        self.哨兵价形成索引 = None
        self.哨兵价本根新形成 = False
        self.哨兵价已确认可执行 = False
        self.待确认哨兵价 = None
        self.待确认哨兵价类型 = None
        # 哨兵价等待成交期间锁定原始信号，避免后续上穿覆盖归因。
        self.哨兵价锁定信号类型 = None
        self._上上根RSI = 50
        
        # 过滤因子追踪变量
        self.MA序列 = []
        self.RSI序列 = []
        self.连续亏损次数 = 0
        self.冷却期剩余K线 = 0
        self.过滤因子列表 = self._加载过滤因子()
        self.过滤运行状态 = {}
        self.哨兵量价快照 = {}
        self.量价历史 = []
                # 加载买入规则模块
        self.买入规则列表 = self._加载买入规则()
        
        # 加载卖出规则模块
        self.卖出规则列表 = self._加载卖出规则()

        # 因子管理器 (所有因子默认关闭，通过因子配置.yaml启用)
        self.因子管理器 = None
        self.全局状态 = {}
        try:
            from 因子模块.因子管理器 import 因子管理器
            self.因子管理器 = 因子管理器(配置目录)
            if self.因子管理器.已启用因子:
                print(f"[规则执行器] 因子管理器就绪")
        except Exception as e:
            print(f"[规则执行器] 因子管理器初始化失败: {e}")
            self.因子管理器 = None

    def _更新哨兵价跟踪(self, K线数据):
        """在没有新哨兵价形成时，只允许旧哨兵价向上跟踪。"""
        if not (
            getattr(self, '哨兵价跟踪启用', self.哨兵价已形成)
            and self.哨兵价当前 is not None
        ):
            return
        if not self._核心模块启用('哨兵价突破后上移', True):
            return
        当前最高 = K线数据.get('前复权_最高', 0)
        try:
            当前最高 = float(当前最高)
            当前哨兵价 = float(self.哨兵价当前)
        except (TypeError, ValueError):
            return
        if 当前最高 <= 当前哨兵价:
            return

        if self.买入时机模式 == STRICT_PRECOMPUTED:
            反推价 = getattr(self, 'RSI反推价当前', None)
            try:
                反推价 = float(反推价) if 反推价 is not None else 当前哨兵价
            except (TypeError, ValueError):
                反推价 = 当前哨兵价
            新哨兵价 = max(反推价, 当前最高)
            if 新哨兵价 <= 当前哨兵价:
                return
            self.哨兵价当前 = 新哨兵价
            self.最终买入触发价当前 = 新哨兵价
            self.上一根突破基准价当前 = 当前最高
            最近成交价 = getattr(self, '最近成交哨兵价', None)
            if 最近成交价 is None or 新哨兵价 > float(最近成交价):
                self.哨兵价可执行 = True
            return

        self.哨兵价当前 = 当前最高
        self.最终买入触发价当前 = 当前最高
        最近成交价 = getattr(self, '最近成交哨兵价', None)
        if 最近成交价 is None or 当前最高 > float(最近成交价):
            self.哨兵价可执行 = True

    def _消费当前哨兵价(self, 成交哨兵价=None):
        """成交只消费当前价格档位；哨兵数值和向上跟踪继续保留。"""
        price = self.哨兵价当前 if 成交哨兵价 is None else 成交哨兵价
        self.哨兵价已消费价格 = price
        self.最近成交哨兵价 = price
        self.哨兵价已形成 = self.哨兵价当前 is not None
        self.哨兵价跟踪启用 = self.哨兵价当前 is not None
        self.哨兵价可执行 = False

    def _加载yaml(self, 文件名):
        """加载YAML配置文件"""
        路径 = os.path.join(self.配置目录, 文件名)
        try:
            with open(路径, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"⚠️  加载配置失败 {文件名}: {e}")
            return {}

    def _核心模块启用(self, 名称, 默认值=True):
        """读取核心模块开关；缺少配置时保持原有行为。"""
        核心模块 = getattr(self, '核心模块', {})
        legacy = bool(核心模块.get(名称, {}).get('启用', 默认值))
        mapping = {
            '反推价计算': 'reverse_price', '哨兵价形成': 'sentinel_build',
            '哨兵价突破成交': 'sentinel_breakout', '哨兵价突破后上移': 'sentinel_trailing',
            '本根形成立即成交': 'same_bar_entry', '下一根执行': 'next_bar_entry',
        }
        module_id = mapping.get(名称)
        manager = getattr(self, '模块开关', None)
        return manager.是否启用('核心模块', module_id, legacy) if manager and module_id else legacy
    
    def _加载买入规则(self):
        """加载启用的买入规则模块"""
        规则列表 = []
        买入信号 = self.买入配置.get('买入信号列表', [])
        
        for 信号 in 买入信号:
            名称 = 信号['英文标识']
            if not self.模块开关.是否启用('买入规则', 名称, 信号.get('启用', False)):
                continue
            try:
                模块 = __import__(f'5_买入规则.{名称}', fromlist=['检查'])
                规则列表.append({
                    "名称": 名称,
                    "模块": 模块,
                    "优先级": 信号.get('优先级', 99),
                    "类型": 信号['名称'],
                    "基础质量分": 信号.get('基础质量分', 0.5),
                    "单笔买入上限": 信号.get('单笔买入上限'),
                    "信号资金系数": float(信号.get('信号资金系数', 1.0) or 1.0),
                    "需要均线上涨确认": 信号.get('需要均线上涨确认', False),
                    "确认K线数":信号.get('确认K线数', 0),
                })
            except Exception as e:
                print(f"⚠️  加载买入规则失败 {名称}: {e}")
        
        # 按优先级排序
        规则列表.sort(key=lambda x: x['优先级'])
        return 规则列表

    def _获取买入规则(self, 信号类型):
        """返回当前信号的完整配置，供哨兵价和仓位检查使用。"""
        return next((r for r in self.买入规则列表 if r['类型'] == 信号类型), None)
    
    def _加载卖出规则(self):
        """加载启用的卖出规则模块"""
        规则列表 = []
        卖出信号 = self.卖出配置.get('卖出条件列表', [])
        
        for 信号 in 卖出信号:
            名称 = 信号['英文标识']
            # 守仓模块是卖出规则的保护层，不是直接触发卖出的规则。
            if 名称 == 'rsi_threshold_hold':
                continue
            if not self.模块开关.是否启用('卖出规则', 名称, 信号.get('启用', False)):
                continue
            try:
                模块 = __import__(f'6_卖出规则.{名称}', fromlist=['检查'])
                规则列表.append({
                    "名称": 名称,
                    "模块": 模块,
                    "检查顺序": 信号.get('检查顺序', 99),
                    "说明": 信号.get('说明', ''),
                    "配置": 信号,  # 保存完整配置，传递给检查函数
                })
            except Exception as e:
                print(f"⚠️  加载卖出规则失败 {名称}: {e}")
        
        规则列表.sort(key=lambda x: x['检查顺序'])
        return 规则列表

    def _更新RSI阈值守仓(self, K线数据):
        """仅用上一根已完成 K 线更新守仓，不引入未来数据。"""
        if not self.RSI阈值守仓启用:
            return
        try:
            模块 = __import__('6_卖出规则.rsi_threshold_hold', fromlist=['更新'])
            self.RSI阈值守仓状态 = 模块.更新(
                self.RSI阈值守仓状态,
                self._上上根RSI,
                K线数据.get('_上一根RSI', 50),
                self.上一根_RSI_MA,
            )
        except Exception as e:
            self.RSI阈值守仓状态 = {"错误": str(e)}
    
    def _加载过滤因子(self):
        """加载启用的过滤因子模块"""
        因子列表 = []
        过滤配置 = self._加载yaml('过滤因子配置.yaml')
        因子信号 = 过滤配置.get('过滤因子列表', [])
        
        for 因子 in 因子信号:
            名称 = 因子['英文标识']
            if not self.模块开关.是否启用('过滤因子', 名称, 因子.get('启用', False)):
                continue
            try:
                模块 = __import__(f'8_过滤因子.{名称}', fromlist=['检查'])
                因子列表.append({
                    "名称": 名称,
                    "模块": 模块,
                    "配置": 因子,
                })
            except Exception as e:
                print(f"⚠️  加载过滤因子失败 {名称}: {e}")
        
        因子列表.sort(key=lambda x: x['配置'].get('检查顺序', 99))
        return 因子列表

    def _检查过滤因子(self, 信号类型, K线数据, 过滤状态):
        """执行 8_过滤因子 中所有已启用因子，并返回完整审计结果。"""
        允许买入 = True
        明细 = []
        分组结果 = {}
        for 因子 in self.过滤因子列表:
            try:
                结果 = 因子['模块'].检查(
                    信号类型, K线数据, 过滤状态, 因子.get('配置', {})
                )
                通过 = bool(结果.get('通过', True))
                明细项 = {
                    '名称': 因子['配置'].get('名称', 因子['名称']),
                    '通过': 通过,
                    '原因': 结果.get('原因', ''),
                }
                明细项.update({key: value for key, value in 结果.items()
                            if key not in ('通过', '原因')})
                明细.append(明细项)
                组合组 = 因子['配置'].get('组合组')
                组合逻辑 = 因子['配置'].get('组合逻辑', '全部通过')
                if 组合组:
                    group = 分组结果.setdefault(组合组, {
                        '逻辑': 组合逻辑, '明细索引': [], '通过': [],
                    })
                    group['明细索引'].append(len(明细) - 1)
                    group['通过'].append(通过)
                    明细项['组合组'] = 组合组
                    明细项['组合逻辑'] = 组合逻辑
                elif not 通过:
                    允许买入 = False
                    明细项['阻拦'] = True
                else:
                    明细项['阻拦'] = False
            except Exception as e:
                # 因子异常按拦截处理，避免故障时无提示地放行交易。
                允许买入 = False
                明细.append({
                    '名称': 因子['配置'].get('名称', 因子['名称']),
                    '通过': False,
                    '阻拦': True,
                    '原因': f'因子执行异常: {e}',
                })
        for group in 分组结果.values():
            logic = group['逻辑']
            passed = any(group['通过']) if logic == '任一通过' else all(group['通过'])
            for index in group['明细索引']:
                明细[index]['组合通过'] = passed
                明细[index]['阻拦'] = not passed
            if not passed:
                允许买入 = False
        return {'允许买入': 允许买入, '明细': 明细}

    def _更新过滤因子状态(self, K线数据):
        """逐根更新有状态过滤因子，买入检查只读取已经完成的数据。"""
        for 因子 in self.过滤因子列表:
            更新函数 = getattr(因子['模块'], '更新', None)
            if 更新函数 is None:
                continue
            try:
                更新函数(K线数据, self.过滤运行状态, 因子.get('配置', {}))
            except Exception as e:
                self.过滤运行状态.setdefault('更新错误', {})[因子['名称']] = str(e)

    def _获取过滤因子状态(self):
        状态 = {}
        for 因子 in self.过滤因子列表:
            获取函数 = getattr(因子['模块'], '获取状态', None)
            if 获取函数 is None:
                continue
            try:
                状态[因子['名称']] = 获取函数(
                    self.过滤运行状态, 因子.get('配置', {})
                )
            except Exception as e:
                状态[因子['名称']] = {'错误': str(e)}
        return 状态

    def _获取RSI信号阈值(self, 信号类型, 默认阈值):
        """Read an optional regime threshold without changing legacy defaults."""
        factor = next(
            (item for item in self.过滤因子列表
             if item.get("名称") == "rsi_regime_adaptive_filter"),
            None,
        )
        if not factor:
            return 默认阈值
        try:
            module = factor["模块"]
            value = module.获取RSI阈值(
                信号类型, self.过滤运行状态, factor.get("配置", {})
            )
            return float(value) if value is not None else 默认阈值
        except (AttributeError, TypeError, ValueError, KeyError):
            return 默认阈值

    def _生成哨兵量价快照(self):
        """保存哨兵形成时的量价证据；不修改哨兵价和订单参数。"""
        config = next(
            (item.get("配置", {}) for item in self.过滤因子列表
             if item.get("名称") == "sentinel_volume_price_filter"),
            {},
        )
        lookback = max(8, int(config.get("回看根数", 8) or 8))
        rows = self.量价历史[-lookback:]
        if len(rows) < 8:
            return {"有效": False, "历史根数": len(rows)}
        volumes = [float(row.get("成交量", 0) or 0) for row in rows]
        closes = [float(row.get("收盘", 0) or 0) for row in rows]
        last = rows[-1]
        price_range = float(last.get("最高", 0) or 0) - float(last.get("最低", 0) or 0)
        close_strength = (
            (float(last.get("收盘", 0)) - float(last.get("最低", 0))) / price_range
            if price_range > 0 else 0.5
        )
        early_volume = float(np.mean(volumes[:5]))
        recent_volume = float(np.mean(volumes[-3:]))
        baseline = float(np.mean(volumes[:-1]))
        return {
            "有效": early_volume > 0 and baseline > 0 and closes[0] > 0,
            "历史根数": len(rows),
            "相对量能": recent_volume / baseline if baseline > 0 else None,
            "缩量比例": recent_volume / early_volume if early_volume > 0 else None,
            "近期价格变化": closes[-1] / closes[-3] - 1 if closes[-3] > 0 else None,
            "趋势涨幅": closes[-1] / closes[-5] - 1 if closes[-5] > 0 else None,
            "单根跌幅": closes[-1] / closes[-2] - 1 if closes[-2] > 0 else None,
            "收盘强度": close_strength,
            "上影比例": (
                (float(last.get("最高", 0)) - max(float(last.get("开盘", 0)), float(last.get("收盘", 0))))
                / price_range if price_range > 0 else 0.0
            ),
            "形成时间": last.get("时间", ""),
            "形成信号": self.哨兵价形成类型,
        }

    def _记录量价历史(self, K线数据):
        """仅保存已完成K线的基础量价字段，供下一次哨兵形成取证。"""
        self.量价历史.append({
            "开盘": K线数据.get("前复权_开盘", K线数据.get("开盘价", 0)),
            "最高": K线数据.get("前复权_最高", K线数据.get("最高价", 0)),
            "最低": K线数据.get("前复权_最低", K线数据.get("最低价", 0)),
            "收盘": K线数据.get("前复权_收盘", K线数据.get("收盘价", 0)),
            "成交量": K线数据.get("成交量", K线数据.get("不复权_成交量", 0)),
            "时间": K线数据.get("完整时间", K线数据.get("日期", "")),
        })
        if len(self.量价历史) > 120:
            self.量价历史.pop(0)

    def _处理每根扩展因子(self, K线数据):
        """更新扩展因子状态；调用位置决定该数据从哪根开始可见。"""
        if not self.因子管理器:
            return
        self.全局状态 = {
            "RSI": K线数据.get("RSI_14"),
            "RSI_MA": K线数据.get("RSI_均线_20"),
            "ATR": K线数据.get("ATR_14"),
            "大盘状态": self.大盘状态 if hasattr(self, "大盘状态") else "震荡模式",
            "有顶背离": self.有顶背离 if hasattr(self, "有顶背离") else False,
            "有底背离": self.有底背离 if hasattr(self, "有底背离") else False,
            "哨兵价形成类型": self.哨兵价形成类型 if hasattr(self, "哨兵价形成类型") else "",
            "当前持仓": self.当前持仓,
            "当前现金": self.当前现金,
        }
        因子结果 = self.因子管理器.每根K线处理(K线数据, self.全局状态)
        if "波动率分类器" in 因子结果:
            self.全局状态["波动率分类"] = 因子结果["波动率分类器"]
        if "大盘状态" in self.全局状态:
            self.大盘状态 = self.全局状态["大盘状态"]
        if "有顶背离" in self.全局状态:
            self.有顶背离 = self.全局状态["有顶背离"]
        if "有底背离" in self.全局状态:
            self.有底背离 = self.全局状态["有底背离"]
    
    def 每根K线处理(self, K线数据, 当前索引):
        """
        处理一根K线
        
        传入:
            K线数据 - 这一根K线的所有数据 (dict或Series)
            当前索引 - 第几根K线
        """
        
        self.已买入K线数 += 1
        self.本根决策 = {
            "买入信号": [], "卖出检查": [], "最终动作": "不交易",
            "动作原因": "没有满足的策略条件",
            "决策记录": {"阶段": "初始化", "信号": {}, "买入": {}, "卖出": {}},
        }
        self.本根反推价 = None
        self.本根反推信号类型 = None
        self.本根反推目标RSI = None
        self._本根哨兵价来源 = None
        self._本根已买入股票 = set()

        # 严格模式的买入判断只能读取上一根累积的过滤状态。
        # 旧版对照仍保留原先的当根更新顺序，便于复现历史结果。
        if not 是严格模式(self.买入时机模式):
            self._更新过滤因子状态(K线数据)
        self._更新RSI阈值守仓(K线数据)

        # 本根预挂模式在开盘前用上一根已完成状态建立订单；本根收盘
        # 后的新 RSI 只能用于下一根，不能回填当前最高价。
        if (self.买入时机模式 in (SAME_BAR_ENTRY, STRICT_PRECOMPUTED)
                or self.网格加仓时机模式 == STRICT_PRECOMPUTED):
            self._预计算本根哨兵价()

        # 严格预挂模式要到本根买卖决策结束后才更新扩展因子。
        if self.买入时机模式 != STRICT_PRECOMPUTED:
            self._处理每根扩展因子(K线数据)

        
        # 记录本根K线
        self.交易记录器.记录本根K线(
            K线索引=当前索引,
            日期=K线数据.get('日期', ''),
            时间=str(getattr(K线数据, 'name', K线数据.get('完整时间', ''))),
            前复权收盘=K线数据.get('前复权_收盘', K线数据.get('收盘价', 0)),
            不复权收盘=K线数据.get('不复权_收盘', K线数据.get('收盘价', 0)),
            RSI值=K线数据.get('RSI_14', 50),
            RSI_MA值=K线数据.get('RSI_均线_20', 50),
            ATR值=K线数据.get('ATR_14', 0),
        )
        
        # 更新价格/RSI序列（用于背离检测）
        前复权收盘 = K线数据.get('前复权_收盘', K线数据.get('收盘价', None))
        RSI价格列对照 = {
            'high': '前复权_最高', 'close': '前复权_收盘', 'low': '前复权_最低'
        }
        RSI基准价格 = K线数据.get(
            RSI价格列对照.get(getattr(self, 'RSI价格源', 'close'), '前复权_收盘'),
            前复权收盘,
        )
        if RSI基准价格 is not None:
            # 反推RSI价位必须使用与RSI相同的价格序列。
            self.价格序列.append(RSI基准价格)
            self.RSI序列.append(K线数据.get('RSI_14', 50))
        rsi_ma_val = K线数据.get("RSI_均线_20", None)
        if rsi_ma_val is not None and not pd.isna(rsi_ma_val):
            self.RSI_MA历史.append(rsi_ma_val)
            if len(self.价格序列) > 120:
                self.价格序列.pop(0)
                self.RSI序列.pop(0)
        
        # 检测背离
        if len(self.价格序列) >= 60:
            try:
                from 策略引擎.背离检测 import 检测背离 as _检测背离
                背离结果 = _检测背离(pd.Series(self.价格序列), pd.Series(self.RSI序列), 查看K线数=60)
                self.有底背离 = 背离结果.get('底背离', False)
                self.有顶背离 = 背离结果.get('顶背离', False)
            except Exception as error:
                self._记录策略异常("背离检测", error, 当前索引)
        
        # 当前K线只负责检查上一根收盘前已经存在的哨兵价。
        # 本标记只描述当前收盘后形成、供下一根使用的信号，不能污染本根买入检查。
        self.哨兵价本根新形成 = False
        本根触发哨兵价 = self.哨兵价当前
        self._本根触发哨兵价 = 本根触发哨兵价
        self._执行待次根开盘卖出(K线数据, 当前索引)
        允许下一根执行 = self._核心模块启用('下一根执行', True)
        待买入已成交 = (
            self._执行待次根开盘买入(K线数据, 当前索引)
            if 允许下一根执行 else False
        )
        if not 待买入已成交 and (允许下一根执行 or self.买入时机模式 == SAME_BAR_ENTRY):
            self._检查买入(K线数据, 当前索引)
        # 跟踪上移：旧哨兵价只允许向上移动；若没有形成新的哨兵价，则不能回退。
        self._更新哨兵价跟踪(K线数据)

        # same_bar_entry 的“本根形成”指本根开始前根据上一根完整数据
        # 预计算并挂出的哨兵价；不能在本根收盘后再用本根 RSI 形成第二个
        # 哨兵价并回看本根最高价成交。
        if self.买入时机模式 != SAME_BAR_ENTRY:
            # 收盘后形成哨兵价；严格模式只保留给后续K线，旧版回放模式
            # 才允许用本根最高价做历史兼容检查。
            self._计算哨兵价(K线数据, 当前索引)
            # 旧版回放模式保留本根收盘后的兼容检查；严格模式禁止回填。
            if (允许旧版本根回填(self.买入时机模式)
                    and self.哨兵价本根新形成
                    and self._核心模块启用('本根形成立即成交', False)
                    and not 待买入已成交):
                self._本根触发哨兵价 = self.哨兵价当前
                self._检查买入(K线数据, 当前索引)
        
        # 检查卖出信号
        # ★ 修复: 预取快照，避免dict突变
        持仓快照 = list(self.当前持仓.items())
        for 股票代码, 持仓 in 持仓快照:
            self._检查卖出(持仓, K线数据, 当前索引, 股票_code=股票代码)

        # 卖出检查之后再检查“加仓”（避免同根同时触发卖出与加仓）
        if (self.因子管理器 and self.因子管理器.已启用因子
                and self.网格加仓时机模式 != SAME_BAR_ENTRY):
            加仓快照 = list(self.当前持仓.items())
            for 股票代码, 持仓 in 加仓快照:
                self._检查加仓(持仓, K线数据, 当前索引, 股票_code=股票代码)
        elif self.因子管理器 and self.因子管理器.已启用因子:
            # 本根模式要等本根收盘形成新哨兵价后再检查网格，避免把
            # 开盘前预计算的上一根哨兵价误当成本根新形成的信号。
            加仓快照 = list(self.当前持仓.items())
            for 股票代码, 持仓 in 加仓快照:
                self._检查加仓(持仓, K线数据, 当前索引, 股票_code=股票代码)

        # 当根收盘数据在本根交易判断结束后才进入过滤状态，
        # 因此只能影响下一根 K 线。
        if 是严格模式(self.买入时机模式):
            self._更新过滤因子状态(K线数据)
        if self.买入时机模式 == STRICT_PRECOMPUTED:
            self._处理每根扩展因子(K线数据)

        # 当前K线结束后，才把本根指标和高点纳入下一根K线的卖出状态。
        当前RSI = K线数据.get('RSI_14', None)
        当前最高 = K线数据.get('前复权_最高', None)
        for 持仓 in self.当前持仓.values():
            if 当前RSI is not None and not pd.isna(当前RSI):
                持仓['RSI峰值'] = max(持仓.get('RSI峰值', 0), 当前RSI)
            if 当前最高 is not None and not pd.isna(当前最高):
                持仓['最高价'] = max(持仓.get('最高价', 0), 当前最高)
        
        # 更新MA序列和RSI序列（供过滤因子使用）
        MA值 = K线数据.get('RSI_均线_20', None)
        if MA值 is not None:
            self.MA序列.append(MA值)
            if len(self.MA序列) > 120:
                self.MA序列.pop(0)
        # RSI序列已在前面更新，不需要重复追加
        self._记录量价历史(K线数据)
        
        # 更新冷却期剩余
        if self.冷却期剩余K线 > 0:
            self.冷却期剩余K线 -= 1
        
        # 保存上一根K线数据（用于反推价突破检查）
        self.上一根_最高价 = K线数据.get('前复权_最高', None)
        self.上一根_RSI_MA = K线数据.get('RSI_均线_20', None)
        self._上上根_RSI_MA = self.上一根_RSI_MA
        self.上一根_最低价 = K线数据.get('前复权_最低', None)
        self.上一根_不复权收盘 = K线数据.get('不复权_收盘', None)
        self.上一根_ATR = K线数据.get('ATR_14', None)
        self._上上根RSI = K线数据.get('_上一根RSI', 50)

        当前持仓市值 = sum(
            _持仓.get('股数', 0) * K线数据.get('不复权_收盘', 0)
            for _持仓 in self.当前持仓.values()
        )
        self.交易记录器.更新本根K线(
            买入信号=self.本根决策.get("买入信号", []),
            过滤检查=self.本根决策.get("过滤检查", []),
            卖出检查=self.本根决策.get("卖出检查", []),
            最终动作=self.本根决策.get("最终动作", "不交易"),
            动作原因=self.本根决策.get("动作原因", ""),
            当前现金=self.当前现金,
            持仓市值=当前持仓市值,
            权益=self.当前现金 + 当前持仓市值,
            持仓数量=sum(_p.get('股数', 0) for _p in self.当前持仓.values()),
            # 页面蓝线显示本根收盘后形成、供下一根使用的哨兵价；
            # 本根实际成交核对使用下方的“本根触发哨兵价”。
            哨兵价=self.哨兵价当前,
            本根触发哨兵价=getattr(self, '_本根触发哨兵价', 本根触发哨兵价),
            RSI反推价当前=self.RSI反推价当前,
            上一根突破基准价=self.上一根突破基准价当前,
            最终买入触发价=self.最终买入触发价当前,
            哨兵价形成类型=self.哨兵价形成类型,
            哨兵价本根新形成=self.哨兵价本根新形成,
            哨兵价已确认可执行=getattr(self, '哨兵价已确认可执行', False),
            哨兵价跟踪启用=getattr(self, '哨兵价跟踪启用', False),
            哨兵价可执行=getattr(self, '哨兵价可执行', False),
            哨兵价已消费价格=getattr(self, '哨兵价已消费价格', None),
            最近成交哨兵价=getattr(self, '最近成交哨兵价', None),
            策略异常=self.本根决策.get("策略异常", []),
            卖出时机模式=self.卖出时机模式,
            待次根开盘卖出=list(self.待次根开盘卖出.keys()),
            本根反推价=self.本根反推价,
            本根反推信号类型=self.本根反推信号类型,
            本根反推目标RSI=self.本根反推目标RSI,
            RSI阈值守仓状态=self.RSI阈值守仓状态 if self.RSI阈值守仓启用 else {},
            扩展因子状态=self._获取过滤因子状态(),
            决策记录=self.本根决策.get("决策记录", {}),
        )
    
    def _预计算本根哨兵价(self):
        """用上一根完整 RSI 状态反推本根买入价，不读取本根收盘。"""
        if not self._核心模块启用('反推价计算', True):
            return
        if len(self.价格序列) < 15 or self.上一根_最高价 is None:
            return
        try:
            # 本方法在当前K线价格追加前调用，因此现有序列本身就是
            # 上一根收盘及更早的完整历史，不能再丢掉最后一根。
            历史价格 = self.价格序列
            历史RSI = self.RSI序列
            上一根RSI = 计算WilderRSI(历史价格[-15:])
            if 上一根RSI is None or pd.isna(上一根RSI):
                return
            阈值20 = self._获取RSI信号阈值("RSI上穿20", 20)
            阈值30 = self._获取RSI信号阈值("RSI上穿30", 30)
            阈值70 = self._获取RSI信号阈值("RSI上穿70", 70)
            if float(上一根RSI) < 阈值20:
                目标RSI = 阈值20
            elif self.上一根_RSI_MA is not None and float(上一根RSI) < float(self.上一根_RSI_MA):
                目标RSI = float(self.上一根_RSI_MA)
            elif float(上一根RSI) < 阈值30:
                目标RSI = 阈值30
            elif float(上一根RSI) < 阈值70:
                目标RSI = 阈值70
            else:
                return
            结果 = 计算Wilder上涨反推价(历史价格[-15:], 目标RSI)
            # Wilder 反推接口返回“RSI反推价”；兼容旧实现的“目标价位”
            # 只作为过渡，避免字段协议不一致时静默变成零交易。
            反推价 = 结果.get('RSI反推价', 结果.get('目标价位'))
            if not 结果.get('可用', 反推价 is not None) or 反推价 is None:
                return
            target = float(结果.get('目标RSI', 目标RSI))
            signal_by_threshold = {
                阈值20: 'RSI上穿20', 阈值30: 'RSI上穿30', 阈值70: 'RSI上穿70',
            }
            信号类型 = signal_by_threshold.get(target, 'RSI上穿均线')
            if 反推价 is None:
                return
            最新价格 = float(历史价格[-1])
            if 最新价格 <= 0 or float(反推价) > 最新价格 * 2:
                return
            if not any(r.get('类型') == 信号类型 for r in self.买入规则列表):
                # RSI均线目标值在历史配置中可能被序列化为浮点数；
                # 归属仍按“上穿均线”处理，而不是误判为未启用。
                if target not in signal_by_threshold:
                    信号类型 = 'RSI上穿均线'
                if not any(r.get('类型') == 信号类型 for r in self.买入规则列表):
                    return
            # 只在上一根数据推导出不同信号时替换旧哨兵，避免每根K线重复重置。
            # 这能清除旧的不可达哨兵，并让上一根收盘已经确定的新哨兵
            # 在本根最高价触发，仍不读取本根收盘或本根 RSI。
            if (self.哨兵价已形成
                    and self.哨兵价当前 is not None
                    and self.哨兵价形成类型 == 信号类型):
                return
            候选 = 形成候选(反推价, self.上一根_最高价)
            self.RSI反推价当前 = 候选['RSI反推价']
            self.上一根突破基准价当前 = 候选['上一根最高价']
            self.最终买入触发价当前 = 候选['触发边界']
            self.哨兵价当前 = 候选['触发边界']
            self.哨兵价已形成 = True
            self.哨兵价跟踪启用 = True
            self.哨兵价可执行 = True
            self.哨兵价已确认可执行 = True
            self.哨兵价形成类型 = 信号类型
            self.哨兵价锁定信号类型 = 信号类型
            self.哨兵价形成索引 = self.已买入K线数
            self.哨兵价本根新形成 = True
            self.哨兵量价快照 = self._生成哨兵量价快照()
            self.本根反推价 = float(反推价)
            self.本根反推信号类型 = 信号类型
            self.本根反推目标RSI = 结果.get('目标RSI')
            self._本根哨兵价来源 = "precomputed"
        except (TypeError, ValueError, KeyError):
            return

    def _检查买入(self, K线数据, 当前索引):
        """检查买入信号 — 价格突破哨兵价即买入（无需RSI触发）"""
        if not self._核心模块启用('哨兵价突破成交', True):
            self.本根决策["动作原因"] = "核心模块已关闭：哨兵价突破成交"
            return
        if self._行情不可交易(K线数据):
            self.本根决策["动作原因"] = "行情缺失、停牌或无成交量，禁止买入"
            return
        if getattr(self, '涨停不买', True) and self._封死涨停(K线数据):
            self.本根决策["动作原因"] = "涨停封死，无可成交卖单，禁止买入"
            return
        
        该股票代码 = K线数据.get('股票代码', '600519')
        if self._账户已达到最大持仓数(该股票代码):
            self.本根决策["动作原因"] = "已达到最大持仓数（新股票被拦截）"
            self._记录账户审批(
                类型="买入", 结果="组合层拦截", 原因="达到最大持仓数量",
                请求股数=0, 成交股数=0,
                时间=str(getattr(K线数据, 'name', K线数据.get('完整时间', K线数据.get('日期', '')))),
            )
            return
        # 普通 RSI 哨兵突破只负责首次开仓。已有持仓后，后续加仓必须先
        # 达到网格回撤层（L1/L2...），再由新的买入信号确认；网格关闭时
        # 则持仓期间不再买入，不能让上涨中的新哨兵突破绕过回撤条件。
        if 该股票代码 in self.当前持仓:
            网格启用 = bool(
                self.因子管理器
                and 'grid_addon' in getattr(self.因子管理器, '已启用因子', {})
            )
            self.本根决策["动作原因"] = (
                "已有持仓，普通RSI买入关闭，等待网格回撤触发"
                if 网格启用 else "已有持仓且网格未启用，禁止继续买入"
            )
            self.本根决策["决策记录"]["阶段"] = "网格等待" if 网格启用 else "持仓等待"
            self.本根决策["决策记录"]["买入"] = {
                "结果": "等待网格回撤" if 网格启用 else "持仓期间禁止普通买入",
                "网格规则": (
                    "持仓后仅允许L1及后续网格加仓"
                    if 网格启用 else "网格关闭，持仓后不允许加仓"
                ),
            }
            return
        if 该股票代码 in getattr(self, '_本根已买入股票', set()):
            self.本根决策["动作原因"] = "同一根K线已经买入，禁止重复普通买入"
            return
        
        if not self.哨兵价已形成 or self.哨兵价当前 is None:
            self.本根决策["动作原因"] = "尚未形成哨兵价"
            return
        if not getattr(self, '哨兵价可执行', self.哨兵价已形成):
            self.本根决策["动作原因"] = "当前哨兵价档位已成交，继续跟踪上移"
            return

        # 过滤：哨兵价形成类型必须在已启用的买入规则中。
        # 优先使用本根预计算信号，避免旧哨兵类型与新信号类型不同步。
        当前信号类型 = self.哨兵价形成类型 or self.本根反推信号类型
        if not any(
            str(规则.get('类型', '')).strip() == str(当前信号类型 or '').strip()
            for 规则 in self.买入规则列表
        ):
            self.本根决策["动作原因"] = "哨兵价对应的买入规则未启用"
            return

        if self.哨兵价形成类型 is None:
            return

        买入时机模式 = 规范化模式(getattr(self, '买入时机模式', STRICT_PRECOMPUTED))
        if 买入时机模式 in (LEGACY_SAME_BAR, TB_REPLAY):
            当前RSI原值 = K线数据.get('RSI_14', 50)
            上一根RSI原值 = K线数据.get('_上一根RSI', 50)
            当前发生上穿 = (
                (上一根RSI原值 < 20 <= 当前RSI原值) or
                (上一根RSI原值 < 30 <= 当前RSI原值) or
                (上一根RSI原值 < 70 <= 当前RSI原值) or
                (self.上一根_RSI_MA is not None and
                 上一根RSI原值 < self.上一根_RSI_MA <= 当前RSI原值)
            )
            if not 哨兵价可执行(买入时机模式, getattr(self, '哨兵价已确认可执行', True), 当前发生上穿):
                self.本根决策["动作原因"] = "旧版哨兵价已预挂，等待当根收盘RSI确认"
                return

        触发明细 = None
        if 买入时机模式 == STRICT_PRECOMPUTED:
            _RSI反推价 = getattr(self, 'RSI反推价当前', None)
            _前高基准 = getattr(self, '上一根突破基准价当前', None)
            触发明细 = 评估触发(
                _RSI反推价 if _RSI反推价 is not None else self.哨兵价当前,
                _前高基准 if _前高基准 is not None else self.哨兵价当前,
                K线数据,
            )
            价格已突破 = bool(触发明细.get('满足'))
            有效触发价 = 触发明细.get('最终买入触发价', self.哨兵价当前)
            self.最终买入触发价当前 = 有效触发价
        else:
            确认价格 = K线数据.get('前复权_收盘', 0) if 使用收盘确认(买入时机模式) else K线数据.get('前复权_最高', 0)
            价格已突破 = bool(确认价格 >= self.哨兵价当前)
            有效触发价 = self.哨兵价当前
        self._本根触发哨兵价 = 有效触发价
        self.本根决策["买入信号"].append({
            "类型": self.哨兵价形成类型,
            "哨兵价": self.哨兵价当前,
            "RSI反推价": getattr(self, 'RSI反推价当前', None),
            "上一根最高价": getattr(self, '上一根突破基准价当前', None),
            "最终买入触发价": 有效触发价,
            "触发明细": 触发明细 or {},
            "本根形成": self.哨兵价本根新形成,
            "价格突破": 价格已突破,
            "满足": 价格已突破,
            "确认方式": "收盘价" if 使用收盘确认(买入时机模式) else "上根预挂、本根价格触发",
        })
        self.本根决策["决策记录"]["阶段"] = "买入检查"
        self.本根决策["决策记录"]["买入"] = {
            "信号类型": self.哨兵价形成类型,
            "哨兵价": self.哨兵价当前,
            "RSI反推价": getattr(self, 'RSI反推价当前', None),
            "上一根最高价": getattr(self, '上一根突破基准价当前', None),
            "最终买入触发价": 有效触发价,
            "触发明细": 触发明细 or {},
            "哨兵形成索引": self.哨兵价形成索引,
            "等待K线数": 当前索引 - self.哨兵价形成索引 if self.哨兵价形成索引 is not None else 0,
            "本根形成": self.哨兵价本根新形成,
            "价格突破": 价格已突破,
            "买入时机模式": 买入时机模式,
        }
        当前买入规则 = self._获取买入规则(self.哨兵价形成类型) or {}
        self.本根决策["决策记录"]["买入"].update({
            "基础质量分": 当前买入规则.get("基础质量分"),
            "单笔买入上限": 当前买入规则.get("单笔买入上限"),
            "信号资金系数": 当前买入规则.get("信号资金系数", 1.0),
        })
        
        # ---- 过滤因子检查（统一在这里拦截） ----
        当前买入规则 = self._获取买入规则(self.哨兵价形成类型)
        信号质量分 = (当前买入规则 or {}).get(
            '基础质量分', self.信号质量对照.get(self.哨兵价形成类型, 0.5)
        )
        
        # 构建公共状态字典（供过滤因子使用）
        过滤状态 = {
            '信号质量分': 信号质量分,
            'MA序列': self.MA序列,
            '连续亏损次数': self.连续亏损次数,
            '冷却期剩余K线': self.冷却期剩余K线,
            '有底背离': self.有底背离,
            '有顶背离': self.有顶背离,
        }
        过滤状态.update(getattr(self, '过滤运行状态', {}))
        过滤状态['哨兵量价快照'] = getattr(self, '哨兵量价快照', {})
        
        def 执行过滤后买入():
            过滤结果 = self._检查过滤因子(
                self.哨兵价形成类型, K线数据, 过滤状态
            )
            self.本根决策['过滤检查'] = 过滤结果['明细']
            if not 过滤结果['允许买入']:
                被拦截 = [
                    x['名称'] for x in 过滤结果['明细']
                    if x.get('阻拦', not x['通过'])
                ]
                self.本根决策['动作原因'] = '过滤因子拦截: ' + '、'.join(被拦截)
                self.本根决策["决策记录"]["阶段"] = "过滤拦截"
                self.本根决策["决策记录"]["买入"]["结果"] = "拦截"
                return False
            self.本根决策["决策记录"]["买入"]["过滤结果"] = "通过"
            return True

        def 执行扩展因子后买入():
            if not self.因子管理器 or not self.因子管理器.已启用因子:
                return True
            当前持仓市值 = sum(
                p.get('股数', 0) * K线数据.get('不复权_开盘', 0)
                for p in self.当前持仓.values()
            )
            self.全局状态.update({
                "信号质量": 信号质量分,
                "总权益": self.当前现金 + 当前持仓市值,
                "当前持仓市值": 当前持仓市值,
                "信号类型": self.哨兵价形成类型,
            })
            因子结果 = self.因子管理器.买入前检查(K线数据, self.全局状态)
            self._本根扩展因子结果 = 因子结果
            self.本根决策["决策记录"]["买入"]["扩展因子"] = 因子结果.get("明细", {})
            if not 因子结果.get("允许买入", True):
                self.本根决策["动作原因"] = "扩展因子拦截: " + 因子结果.get("说明", "")
                self.本根决策["决策记录"]["阶段"] = "扩展因子拦截"
                self.本根决策["决策记录"]["买入"]["结果"] = "拦截"
                return False
            return True

        # 无论哨兵价是否刚形成，都必须由当前K线价格达到后才能成交。
        if not 价格已突破:
            self.本根决策["动作原因"] = (
                "已有哨兵价，但本根收盘价尚未确认突破"
                if 使用收盘确认(买入时机模式)
                else "已有哨兵价，但本根最高价尚未达到"
            )
            return  # 价格未达到哨兵价
        
        if not 执行过滤后买入():
            return
        self._本根扩展因子结果 = {}
        if not 执行扩展因子后买入():
            return
        # 买入决策不能读取当前K线收盘指标；仅保留上一根已完成K线的RSI作记录。
        当前RSI = K线数据.get('_上一根RSI', 50)
        if 使用收盘确认(买入时机模式):
            self.待次根开盘买入 = {
                "哨兵价": self.哨兵价当前,
                "信号类型": self.哨兵价形成类型,
                "信号质量分": 信号质量分 * self._本根扩展因子结果.get('质量分调整', 1.0),
                "建议仓位": self._本根扩展因子结果.get('建议仓位'),
                "RSI": K线数据.get('RSI_14', 当前RSI),
                "确认索引": 当前索引,
            }
            self.哨兵价可执行 = False
            self.本根决策["最终动作"] = "等待次根开盘买入"
            self.本根决策["动作原因"] = "收盘价确认突破，下一根K线开盘执行"
            self.本根决策["决策记录"]["阶段"] = "收盘确认"
            self.本根决策["决策记录"]["买入"]["结果"] = "等待次根开盘"
            return
        已买入 = self._执行买入(规则=None, K线数据=K线数据, 当前索引=当前索引,
                        当前RSI=当前RSI,
                        哨兵价=有效触发价,
                        信号类型=self.哨兵价形成类型,
                        信号质量分=信号质量分 * self._本根扩展因子结果.get('质量分调整', 1.0),
                        建议仓位=self._本根扩展因子结果.get('建议仓位'))
        if 已买入:
            self.哨兵价锁定信号类型 = None
            self._消费当前哨兵价(有效触发价)
            self.RSI反推价当前 = None
            self.上一根突破基准价当前 = None
            self.最终买入触发价当前 = None
            self.本根决策["最终动作"] = "买入"
            self.本根决策["动作原因"] = f"价格突破{self.哨兵价形成类型}哨兵价"
            self.本根决策["决策记录"]["阶段"] = "买入成交"
            self.本根决策["决策记录"]["买入"]["结果"] = "成交"
        else:
            _拒绝原因 = self.本根决策.get("决策记录", {}).get("买入", {}).get("成交拒绝原因")
            self.本根决策["动作原因"] = (
                f"价格已突破哨兵价，但买入执行未成交：{_拒绝原因}"
                if _拒绝原因 else "价格已突破哨兵价，但买入执行未成交"
            )
            self.本根决策["决策记录"]["买入"]["结果"] = "未成交"
   
    def _执行待次根开盘卖出(self, K线数据, 当前索引):
        """执行上一根收盘后确认的卖出订单；成交价只取本根开盘价。"""
        if self.卖出时机模式 != 'next_bar_open' or not self.待次根开盘卖出:
            return False
        已执行 = False
        待处理 = list(self.待次根开盘卖出.items())
        for 股票代码, 待单 in 待处理:
            持仓 = self.当前持仓.get(股票代码)
            if not 持仓:
                self.待次根开盘卖出.pop(股票代码, None)
                continue
            if self._行情不可交易(K线数据) or self._封死跌停(K线数据):
                continue
            规则 = 待单.get('规则') or {'说明': '上一根触发，本根开盘卖出'}
            成交 = self._执行卖出(
                持仓, 规则, float(待单.get('盈亏比例', 0.0) or 0.0),
                K线数据, 触发价=None, 股票代码=股票代码,
                卖出比例=待单.get('卖出比例', 1.0),
            )
            if not 成交:
                continue
            self.待次根开盘卖出.pop(股票代码, None)
            self.本根决策['最终动作'] = '卖出'
            self.本根决策['动作原因'] = '上一根触发，本根开盘执行'
            self.本根决策.setdefault('决策记录', {}).setdefault('卖出', {}).update({
                '结果': '成交',
                '执行方式': '下一根K线开盘',
                '原触发价': 待单.get('触发价'),
            })
            已执行 = True
        return 已执行

    def _执行待次根开盘买入(self, K线数据, 当前索引):
        """将上一根收盘确认的信号在本根开盘执行。"""
        待买 = self.待次根开盘买入
        if not 待买 or 当前索引 <= 待买.get('确认索引', -1):
            return False
        self.待次根开盘买入 = None
        股票代码 = K线数据.get('股票代码', '600519')
        if 股票代码 in self.当前持仓 or self._行情不可交易(K线数据):
            self.本根决策["动作原因"] = "次根开盘无法交易，待买入信号取消"
            return False
        if self.涨停不买 and self._封死涨停(K线数据):
            self.本根决策["动作原因"] = "次根开盘封死涨停，待买入信号取消"
            return False
        已买入 = self._执行买入(
            规则=None, K线数据=K线数据, 当前索引=当前索引,
            当前RSI=待买.get('RSI', 50), 哨兵价=待买['哨兵价'],
            信号类型=待买['信号类型'], 信号质量分=待买['信号质量分'],
            建议仓位=待买.get('建议仓位'), 按开盘成交=True,
        )
        if 已买入:
            self._消费当前哨兵价(待买['哨兵价'])
            self.本根决策["最终动作"] = "买入"
            self.本根决策["动作原因"] = "上一根收盘确认，本根开盘成交"
            self.本根决策["决策记录"]["阶段"] = "次根开盘成交"
        return bool(已买入)

    def _执行买入(self, 规则, K线数据, 当前索引, 当前RSI, 哨兵价=None,
              信号类型=None, 信号质量分=None, 建议仓位=None, 按开盘成交=False,
              指定股数=None, 指定金额=None, 成交模式="breakout", 最大成交价=None):
        """执行买入"""
        股票代码 = K线数据.get('股票代码', '600519')
        if (self.运行参数.get("市场评分禁止新开仓", False)
                and 股票代码 not in self.当前持仓):
            self.本根决策["动作原因"] = "该股票当前不在历史成分股池，禁止新开仓或加仓"
            self.本根决策.setdefault("决策记录", {}).setdefault("买入", {})[
                "成交拒绝原因"
            ] = self.本根决策["动作原因"]
            return False
        前复权开盘 = K线数据.get('前复权_开盘', 0)
        不复权开盘 = K线数据.get('不复权_开盘', 0)
        前复权收盘 = K线数据.get('前复权_收盘', 0)
        不复权收盘 = self.上一根_不复权收盘 or K线数据.get('不复权_收盘', 0)
        
        if 前复权开盘 <= 0 or 不复权开盘 <= 0:
            self.本根决策["动作原因"] = "价格无效，买入未成交"
            return False
        
        # 如果未传入哨兵价，计算反推价作为备用（向后兼容）
        if 哨兵价 is None:
            反推哨兵价 = None
            if len(self.价格序列) >= 16:
                try:
                    前窗口15 = self.价格序列[-16:-1]
                    if not np.any(np.isnan([x for x in 前窗口15 if x is not None])):
                        结果 = 智能反推(前窗口15, RSI_MA_上一根=self.上一根_RSI_MA)
                        反推哨兵价 = 结果.get('目标价位')
                except Exception as error:
                    self._记录策略异常("买入反推备用", error, 当前索引)
            哨兵价 = 反推哨兵价 if 反推哨兵价 is not None else 前复权收盘
        
        self.交易记录器.记录信号K线(
            开盘=K线数据.get('前复权_开盘', 0),
            收盘=前复权收盘,
            最高=K线数据.get('前复权_最高', 0),
            最低=K线数据.get('前复权_最低', 0),
        )
        self.交易记录器.设置哨兵价(哨兵价)

        # 同根成交必须先证明市场实际触及哨兵价。旧版 same_bar_entry
        # 分支会直接计算计划价，可能在最高价未到哨兵价时虚构成交。
        # 下一根开盘执行属于上一根已确认突破后的挂单，不在这里重复判断。
        if not 按开盘成交:
            try:
                当前最高价 = float(K线数据.get('前复权_最高'))
                当前哨兵价 = float(哨兵价)
            except (TypeError, ValueError):
                当前最高价 = None
                当前哨兵价 = None
            if (当前最高价 is None or 当前哨兵价 is None
                    or 当前最高价 < 当前哨兵价):
                self.本根决策["动作原因"] = (
                    f"最高价{当前最高价 if 当前最高价 is not None else '--'}"
                    f"未达到哨兵价{当前哨兵价 if 当前哨兵价 is not None else '--'}，买入未成交"
                )
                self.本根决策.setdefault("决策记录", {}).setdefault("买入", {})[
                    "成交拒绝原因"
                ] = self.本根决策["动作原因"]
                return False
        
        # 计算仓位（使用传入的信号质量分，或重新计算）
        if 信号质量分 is not None:
            信号质量 = 信号质量分
        else:
            try:
                from 策略引擎.信号质量评分 import 评分 as _信号评分
                综合分, 评分明细 = _信号评分(
                    信号类型=self.哨兵价形成类型,
                    大盘状态=self.大盘状态,
                    有底背离=self.有底背离,
                    有顶背离=self.有顶背离,
                    波动率调整=1.0,
                )
                信号质量 = 综合分
            except Exception as e:
                信号质量 = self.信号质量对照.get(self.哨兵价形成类型, 0.5)
        
        # LightGBM预测器调整质量分 (方案C)
        当前RSI_MA = K线数据.get("RSI_均线_20", None)
        if self.预测器 and self.预测器.model and 当前RSI_MA is not None and not pd.isna(当前RSI_MA):
            ma_slope_5 = None
            ma_slope_10 = None
            if len(self.RSI_MA历史) >= 6:
                ma_slope_5 = 当前RSI_MA - self.RSI_MA历史[-6]
            if len(self.RSI_MA历史) >= 11:
                ma_slope_10 = 当前RSI_MA - self.RSI_MA历史[-11]
            预测结果 = self.预测器.预测(
                rsi=当前RSI, rsi_ma=当前RSI_MA,
                atr=K线数据.get("ATR_14"),
                volume=K线数据.get("成交量"),
                ma_slope_5=ma_slope_5, ma_slope_10=ma_slope_10,
                信号类型=信号类型 or (self.哨兵价形成类型 if hasattr(self, "哨兵价形成类型") else ""),
                信号质量分=信号质量,
                前复权收盘=前复权收盘,
            )
            self.预测器调用次数 += 1
            prob = 预测结果["真突破概率"]
            # 方案C: 概率低不买 — prob<0.3跳过当前信号 (已屏蔽)
            # if prob < 0.3:
            #     self.预测器跳过次数 += 1
            #     return  # 跳过本次买入
        # 个股1万元开仓，超出1万元以100股起步
        # 持股数量不限制，总资产3000万
        
        # 严格成交：溢价后高于当根最高价就不成交，不再用 min
        # 把不可成交的订单乐观地压回最高价。
        if 规范化模式(getattr(self, '买入时机模式', STRICT_PRECOMPUTED)) in (LEGACY_SAME_BAR, TB_REPLAY):
            买入基准前复权 = 前复权开盘 if 按开盘成交 else max(前复权开盘, 哨兵价)
            前复权最高 = K线数据.get('前复权_最高', 买入基准前复权)
            前复权成交价 = 买入基准前复权 * self.买入溢价
            if 前复权最高 and 前复权最高 >= 买入基准前复权:
                前复权成交价 = min(前复权成交价, 前复权最高)
        else:
            if 成交模式 == "pullback":
                成交结果 = 计算回撤买入成交(
                    K线数据.get('前复权_开盘'), K线数据.get('前复权_最高'),
                    K线数据.get('前复权_最低'), 哨兵价, self.买入溢价,
                )
            else:
                成交结果 = 计算买入成交(
                    K线数据.get('前复权_开盘'), K线数据.get('前复权_最高'),
                    K线数据.get('前复权_最低'), 哨兵价, self.买入溢价, 按开盘成交,
                )
            if not 成交结果.get('可成交'):
                self.本根决策["动作原因"] = 成交结果.get('原因', '严格成交模型拒绝成交')
                self.本根决策["决策记录"]["买入"]["成交拒绝原因"] = self.本根决策["动作原因"]
                return False
            买入基准前复权 = 成交结果['基准价']
            前复权成交价 = 成交结果['成交价']
        if 最大成交价 is not None:
            try:
                价格上限 = float(最大成交价)
            except (TypeError, ValueError):
                价格上限 = None
            if 价格上限 is not None and 前复权成交价 > 价格上限:
                self.本根决策["动作原因"] = (
                    f"成交价{前复权成交价:.4f}高于加仓价格上限{价格上限:.4f}，加仓未成交"
                )
                self.本根决策["决策记录"]["买入"]["成交拒绝原因"] = self.本根决策["动作原因"]
                return False
        买入基准不复权 = 前复权成交价 * (不复权开盘 / 前复权开盘) if 前复权开盘 > 0 else 不复权开盘
        # 复权触发价可以保留高精度，但实际不复权成交价必须符合股票报价步长。
        买入价 = round(float(买入基准不复权), 2)
        
        # 买入金额受仓位基础金额和信号自身上限共同限制。
        股票代码 = str(K线数据.get('股票代码', '600519')).strip().upper()
        网格加仓 = (
            str(信号类型 or '').startswith('网格加仓')
            and (指定股数 is not None or 指定金额 is not None)
        )
        最低交易单位 = self._最低交易单位(股票代码)
        一手金额 = 买入价 * 最低交易单位
        当前规则 = self._获取买入规则(信号类型 or self.哨兵价形成类型)
        单笔上限 = 当前规则.get('单笔买入上限') if 当前规则 else None
        信号资金系数 = float(当前规则.get('信号资金系数', 1.0) or 1.0) if 当前规则 else 1.0
        信号资金系数 = max(0.01, min(信号资金系数, 1.0))
        目标金额 = self.基础单只金额
        if 建议仓位 is not None:
            if float(建议仓位) <= 0:
                self.本根决策["动作原因"] = "扩展仓位因子建议仓位为0"
                return False
            目标金额 = float(建议仓位)
        if 单笔上限 is not None and 指定股数 is None and 指定金额 is None:
            目标金额 = min(目标金额, float(单笔上限))
        if not 网格加仓 and 指定股数 is None and 指定金额 is None:
            目标金额 *= 信号资金系数
        当前估值价 = 不复权开盘
        结构性可用金额, 账户限制 = self._计算账户结构性可用金额(当前估值价)
        流动性金额上限 = None
        if getattr(self, '流动性上限比例', None) is not None:
            try:
                流动性比例 = float(self.流动性上限比例)
            except (TypeError, ValueError):
                流动性比例 = 0.0
            if 流动性比例 > 0:
                try:
                    上一交易日成交额 = float(K线数据.get('_上一交易日成交额'))
                except (TypeError, ValueError):
                    上一交易日成交额 = 0.0
                流动性金额上限 = max(0.0, 上一交易日成交额 * 流动性比例)
                if 流动性金额上限 <= 0:
                    self.本根决策["动作原因"] = "缺少上一交易日成交额，无法通过买入流动性检查"
                    self._记录账户审批(
                        类型="买入", 结果="组合层拦截", 原因="缺少上一交易日成交额",
                        请求股数=0, 成交股数=0, 成交价=买入价,
                        时间=str(getattr(K线数据, 'name', K线数据.get('完整时间', K线数据.get('日期', '')))),
                    )
                    return False
                账户限制['买入流动性上限'] = 流动性金额上限
        if getattr(self, '单股全仓模式', False):
            结构性可用金额 = max(0.0, self.当前现金)
            网格启用 = bool(
                self.因子管理器
                and 'grid_addon' in getattr(self.因子管理器, '已启用因子', {})
            )
            if 指定金额 is not None:
                买入金额上限 = 结构性可用金额
            else:
                买入金额上限 = min(结构性可用金额, 目标金额) if 网格启用 else 结构性可用金额
            # 修复：单股全仓模式不应无条件忽略“单笔买入上限”。
            # 否则首笔会直接用尽现金，导致网格加仓/后续信号无法再买入（不足一手）。
            if 指定股数 is None and 指定金额 is None and 单笔上限 is not None:
                try:
                    买入金额上限 = min(买入金额上限, float(单笔上限))
                except (TypeError, ValueError):
                    pass
        elif 指定股数 is not None or 指定金额 is not None:
            # 网格加仓的指定股数/金额不受“基础单只金额”限制，只受结构性风控与现金限制。
            买入金额上限 = 结构性可用金额
        else:
            买入金额上限 = min(max(10000, 目标金额), 结构性可用金额)
        if 流动性金额上限 is not None:
            买入金额上限 = min(买入金额上限, 流动性金额上限)
        if 指定股数 is not None:
            请求股数 = max(
                最低交易单位,
                int(float(指定股数) / 最低交易单位) * 最低交易单位,
            )
        elif 指定金额 is not None:
            请求金额 = max(0.0, float(指定金额))
            请求股数 = max(
                最低交易单位,
                int(请求金额 / 买入价 / 最低交易单位) * 最低交易单位,
            )
        else:
            请求金额 = (
                买入金额上限
                if getattr(self, '单股全仓模式', False) and not 网格启用
                else max(10000, 目标金额)
            )
            请求股数 = max(
                最低交易单位,
                int(请求金额 / 买入价 / 最低交易单位) * 最低交易单位,
            )
        # 单股正式模型保留原有1万元结构性最低金额保护。
        # 多股等额资金池可能低于1万元，但只要仍能买入一手，不能把
        # 所有信号统一拦截；该分支只由多股回测运行参数显式开启。
        最低结构性金额 = 100.0 if getattr(self, '运行参数', {}).get('多股资金池模式', False) else 10000.0
        if not 网格加仓 and 结构性可用金额 < 最低结构性金额:
            self.本根决策["动作原因"] = "仓位限制或现金底线导致可买金额不足"
            self._记录账户审批(
                类型="买入", 结果="组合层拦截", 原因="仓位限制或现金底线",
                请求股数=请求股数, 成交股数=0, 成交价=买入价,
                账户限制=账户限制,
                时间=str(getattr(K线数据, 'name', K线数据.get('完整时间', K线数据.get('日期', '')))),
            )
            return False
        # 单笔信号上限不足一手时，仍按最低交易单位买入一手；
        # 结构性仓位和现金限制仍必须满足。
        if 指定股数 is not None:
            try:
                股数 = int(float(指定股数))
            except (TypeError, ValueError):
                股数 = 0
            股数 = max(最低交易单位, int(股数 / 最低交易单位) * 最低交易单位)
        elif 指定金额 is not None:
            股数 = max(
                最低交易单位,
                int(min(float(指定金额), 买入金额上限) / 买入价 / 最低交易单位) * 最低交易单位,
            )
        else:
            股数 = max(最低交易单位, int(买入金额上限 / 买入价 / 最低交易单位) * 最低交易单位)
            if 股数 < 最低交易单位 and 结构性可用金额 >= 一手金额:
                股数 = 最低交易单位
        if 网格加仓:
            # 网格的目标股数仍由统一网格状态机决定，但共享账户的现金、
            # 单股和总仓位限制必须同样生效，不能出现组合现金为负。
            买入金额上限 = 结构性可用金额
            if 流动性金额上限 is not None:
                买入金额上限 = min(买入金额上限, 流动性金额上限)
            预估现金上限 = min(self.当前现金, 结构性可用金额)
        else:
            预估现金上限 = self.当前现金 if getattr(self, '单股全仓模式', False) else 结构性可用金额
        while 股数 >= 最低交易单位:
            实际金额 = 股数 * 买入价
            买入佣金 = max(实际金额 * self.佣金率, 5)
            买入过户费 = 实际金额 * self.过户费率
            买入费用 = 买入佣金 + 买入过户费
            实际金额总 = 实际金额 + 买入费用
            if (实际金额 <= 买入金额上限
                    and 实际金额总 <= 预估现金上限
                    and (网格加仓 or self.当前现金 >= 实际金额总)):
                break
            股数 -= 最低交易单位

        if (股数 < 最低交易单位 and 结构性可用金额 >= 一手金额
                and (流动性金额上限 is None or 流动性金额上限 >= 一手金额)):
            股数 = 最低交易单位
            实际金额 = 股数 * 买入价
            买入佣金 = max(实际金额 * self.佣金率, 5)
            买入过户费 = 实际金额 * self.过户费率
            买入费用 = 买入佣金 + 买入过户费
            实际金额总 = 实际金额 + 买入费用

        if 股数 < 最低交易单位:
            self.本根决策["动作原因"] = "可买数量不足一手"
            self._记录账户审批(
                类型="买入", 结果="组合层拦截", 原因="资金不足一手",
                请求股数=请求股数, 成交股数=0, 成交价=买入价,
                账户限制=账户限制,
                最低交易单位=最低交易单位,
                最低一手含费用=round(float(一手金额 + max(一手金额 * self.佣金率, 5) + 一手金额 * self.过户费率), 2),
                买入金额上限=round(float(买入金额上限), 2),
                当前现金=round(float(self.当前现金), 2),
                时间=str(getattr(K线数据, 'name', K线数据.get('完整时间', K线数据.get('日期', '')))),
            )
            return False
        
        if 实际金额总 > 预估现金上限:
            self.本根决策["动作原因"] = (
                f"最低一手总成本{实际金额总:.2f}元超过仓位或现金可用额"
            )
            self._记录账户审批(
                类型="买入", 结果="组合层拦截", 原因="最低一手总成本超过账户可用额",
                请求股数=请求股数, 成交股数=0, 成交价=买入价,
                账户限制=账户限制, 最低一手含费用=round(float(实际金额总), 2),
                买入金额上限=round(float(买入金额上限), 2),
                当前现金=round(float(self.当前现金), 2),
                时间=str(getattr(K线数据, 'name', K线数据.get('完整时间', K线数据.get('日期', '')))),
            )
            return False
        if not 网格加仓 and self.当前现金 < 实际金额总:
            self.本根决策["动作原因"] = f"现金不足，买入总支出{实际金额总:.2f}"
            self._记录账户审批(
                类型="买入", 结果="组合层拦截", 原因="现金余额不足",
                请求股数=请求股数, 成交股数=0, 成交价=买入价,
                账户限制=账户限制, 最低一手含费用=round(float(实际金额总), 2),
                买入金额上限=round(float(买入金额上限), 2),
                当前现金=round(float(self.当前现金), 2),
                时间=str(getattr(K线数据, 'name', K线数据.get('完整时间', K线数据.get('日期', '')))),
            )
            return False
        if 实际金额 > 买入金额上限:
            self.本根决策["动作原因"] = (
                f"单笔上限{买入金额上限:.2f}元不足一手，按最低一手成交"
            )
        if (getattr(self, '运行参数', {}).get('共享账户模式', False)
                and not getattr(self, '运行参数', {}).get('允许部分成交', True)
                and 股数 < 请求股数):
            self.本根决策["动作原因"] = "组合资金约束只能部分成交，但当前配置禁止部分成交"
            self._记录账户审批(
                类型="买入", 结果="组合层拦截", 原因="禁止部分成交",
                请求股数=请求股数, 成交股数=0, 成交价=买入价,
                账户限制=账户限制,
                时间=str(getattr(K线数据, 'name', K线数据.get('完整时间', K线数据.get('日期', '')))),
            )
            return False
        
        # 记录持仓（支持加仓：同一股票再次买入视为增持，不覆盖原持仓）
        if 股票代码 in self.当前持仓:
            原持仓 = self.当前持仓[股票代码]
            原股数 = int(原持仓.get('股数', 0) or 0)
            新股数 = 原股数 + 股数
            if 新股数 <= 0:
                self.本根决策["动作原因"] = "加仓后股数异常"
                return False

            # 更新成本与股数
            原持仓['股数'] = 新股数
            原持仓['成本'] = float(原持仓.get('成本', 0) or 0) + 实际金额
            原持仓['总成本'] = float(原持仓.get('总成本', 原持仓.get('成本', 0)) or 0) + 实际金额总
            原持仓['买入费用'] = float(原持仓.get('买入费用', 0) or 0) + 买入费用

            # 更新（不复权/前复权）均价：用于止损/止盈等规则更贴近真实成本
            try:
                原买入价 = float(原持仓.get('买入价', 买入价) or 买入价)
                原前复权价 = float(原持仓.get('前复权成交价', 原持仓.get('前复权买入价', 前复权成交价)) or 前复权成交价)
            except (TypeError, ValueError):
                原买入价 = 买入价
                原前复权价 = 前复权成交价
            原持仓['买入价'] = (原买入价 * 原股数 + 买入价 * 股数) / max(新股数, 1)
            原持仓['前复权成交价'] = (原前复权价 * 原股数 + 前复权成交价 * 股数) / max(新股数, 1)
            原持仓['前复权买入价'] = 原持仓['前复权成交价']

        # 网格字段：在加仓成交时推进次数；回撤锚点始终保持首次买入价。
            原持仓['网格_已加仓次数'] = int(原持仓.get('网格_已加仓次数', 0) or 0) + 1
            原持仓['网格_最近加仓索引'] = 当前索引
        else:
            # 同一持仓周期的所有成交（首次开仓及后续网格加仓）共享一个关联ID。
            # 该ID用于回放把每笔买入连接到同一次全仓卖出。
            持仓组ID = f"G{self.交易记录器.买入序号 + 1:06d}"
            self.当前持仓[股票代码] = {
                "买入时间": self.已买入K线数,
                "买入价": 买入价,
                "前复权买入价": 买入基准前复权,
                "前复权成交价": 前复权成交价,
                "股数": 股数,
                "成本": 实际金额,
                "总成本": 实际金额总,
                "买入费用": 买入费用,
                "RSI峰值": 当前RSI,
                "最高价": 买入基准前复权,  # 初始化为买入价，后市上涨时更新
                # 记录开仓信号信息，供加仓/过滤复用
                "信号类型": 信号类型 or self.哨兵价形成类型,
                "信号资金系数": 信号资金系数,
                "信号质量分": 信号质量,
                # 网格加仓状态（不含首次开仓）
                "网格_首次买入价": float(前复权成交价),
                "网格_首笔股数": 股数,
                "网格_已加仓次数": 0,
                "网格_已触发次数": 0,
                "网格_待加仓股数": 0,
                "网格_待加仓金额": 0.0,
                "网格_待加仓层级": [],
                "网格_待单形成索引": None,
                # 兼容旧回放字段；新逻辑使用固定的首次买入价锚点。
                "网格_最近加仓索引": 当前索引,
                "网格_基准最高价": float(前复权成交价),
                "持仓组ID": 持仓组ID,
            }

        持仓组ID = self.当前持仓[股票代码].get('持仓组ID')
        网格级别 = int(self.当前持仓[股票代码].get('网格_已加仓次数', 0) or 0)
        加仓后总持仓 = int(self.当前持仓[股票代码].get('股数', 股数) or 股数)
        
        self.当前现金 -= 实际金额总
        
        # 记录交易
        self.交易记录器.记录买入(
            买入价=买入价,
            信号类型=信号类型 or self.哨兵价形成类型,
            信号质量分=信号质量,
            仓位=实际金额,
            哨兵价=哨兵价,
            哨兵价触发价=哨兵价,
            前复权买入价=买入基准前复权,
            前复权成交价=前复权成交价,
            日期=K线数据.get('日期', ''),
            时间=str(getattr(K线数据, 'name', '') or ''),
            成交数量=股数,
            交易费用=买入费用,
            总成本=实际金额总,
            持仓组ID=持仓组ID,
            网格级别=网格级别,
            加仓后总持仓=加仓后总持仓,
        )
        self.本根决策["决策记录"]["买入"].update({
            "成交价": 买入价,
            "成交数量": 股数,
            "成交金额": 实际金额,
            "交易费用": 买入费用,
            "信号质量分": 信号质量,
            "账户限制": 账户限制,
        })
        self.交易记录器.更新交易记录(
            self.交易记录器.买入序号, '买入',
            买入决策记录=self.本根决策.get('决策记录', {}),
            交易费用=买入费用,
            总成本=实际金额总,
        )
        限制名称 = min(
            ("单只股票仓位", "总仓位", "现金底线"),
            key=lambda name: {
                "单只股票仓位": 账户限制.get("单只结构性上限", float('inf')),
                "总仓位": 账户限制.get("总仓位剩余", float('inf')),
                "现金底线": 账户限制.get("现金可用金额", float('inf')),
            }[name],
        )
        self._记录账户审批(
            类型="买入",
            结果="实际成交",
            审批状态="部分成交" if 股数 < 请求股数 else "全部成交",
            原因=限制名称 if 股数 < 请求股数 else "账户批准",
            请求股数=请求股数,
            成交股数=股数,
            成交价=买入价,
            交易费用=买入费用,
            成交净额=实际金额总,
            网格层级=网格级别,
            信号类型=信号类型 or self.哨兵价形成类型,
            账户限制=账户限制,
            时间=str(getattr(K线数据, 'name', K线数据.get('完整时间', K线数据.get('日期', '')))),
        )
        if not hasattr(self, '_本根已买入股票'):
            self._本根已买入股票 = set()
        self._本根已买入股票.add(股票代码)
        return True
    
    def _计算哨兵价(self, K线数据, 当前索引):
        """
        计算每根K线的哨兵价（独立于买入卖出逻辑，持续跟踪）
        
        逻辑：
        1. 检测RSI上穿阈值 (20 → MA → 30 → 70)
        2. 如果上穿，用反推RSI价位计算反推价
        3. 哨兵价 = max(反推价, 上一根K线最高价)
        4. 如果没有上穿但哨兵价已形成，跟踪上移
        """
        if not self._核心模块启用('反推价计算', True):
            self.本根决策["动作原因"] = "核心模块已关闭：反推价计算"
            return
        if not self._核心模块启用('哨兵价形成', True):
            self.本根决策["动作原因"] = "核心模块已关闭：哨兵价形成"
            return
        前复权高 = K线数据.get('前复权_最高', 0)
        当前RSI = K线数据.get('RSI_14', 50)
        上一根RSI = K线数据.get('_上一根RSI', 50)
        # 重置本根新形成标记（在检测到上穿形成哨兵价时设为True）
        self.哨兵价本根新形成 = False

        # 检查 RSI 上穿（优先级：20 → MA → 30 → 70）。哨兵价属于
        # 信号层记录：每次有效上穿都必须形成/更新哨兵，成交过滤在后续
        # 买入检查中单独处理，不能反过来抑制哨兵形成。
        _上穿阈值 = None
        _上穿类型 = None
        当前RSI_MA = K线数据.get('RSI_均线_20')
        
        阈值20 = self._获取RSI信号阈值("RSI上穿20", 20)
        阈值30 = self._获取RSI信号阈值("RSI上穿30", 30)
        阈值70 = self._获取RSI信号阈值("RSI上穿70", 70)
        if 上一根RSI <= 阈值20 and 当前RSI > 阈值20:
            _上穿阈值 = 阈值20
            _上穿类型 = "RSI上穿20"
        elif (self.上一根_RSI_MA is not None and 当前RSI_MA is not None
              and not pd.isna(当前RSI_MA)
              and 上一根RSI <= self.上一根_RSI_MA and 当前RSI > 当前RSI_MA):
            _上穿阈值 = 当前RSI_MA
            _上穿类型 = "RSI上穿均线"
        elif 上一根RSI <= 阈值30 and 当前RSI > 阈值30:
            _上穿阈值 = 阈值30
            _上穿类型 = "RSI上穿30"
        elif 上一根RSI <= 阈值70 and 当前RSI > 阈值70:
            _上穿阈值 = 阈值70
            _上穿类型 = "RSI上穿70"
        
        _本根实际上穿 = _上穿阈值 is not None

        # 收盘后预挂下一档目标：例如本根 RSI=28.7，尚未上穿30，
        # 但下一根应提前计算“目标 RSI=30”的反推价。下一根只读取
        # 当前最高价判断是否突破，不再用下一根收盘 RSI 重新形成哨兵价。
        # 已有未成交哨兵时保持原值，避免每根K线重算导致哨兵价漂移或下移。
        if (_上穿阈值 is None and not self.哨兵价已形成
                and not self.哨兵价本根新形成):
            try:
                _当前值 = float(当前RSI)
                _均线值 = float(self.上一根_RSI_MA) if self.上一根_RSI_MA is not None else None
                if _当前值 < 阈值20:
                    _上穿阈值, _上穿类型 = 阈值20, "RSI上穿20"
                elif _当前值 < 阈值30:
                    _上穿阈值, _上穿类型 = 阈值30, "RSI上穿30"
                elif _均线值 is not None and _当前值 < _均线值:
                    _上穿阈值, _上穿类型 = _均线值, "RSI上穿均线"
                elif _当前值 < 阈值70:
                    _上穿阈值, _上穿类型 = 阈值70, "RSI上穿70"
            except (TypeError, ValueError):
                pass

        if _本根实际上穿 and len(self.价格序列) >= 16:
            当前规则 = self._获取买入规则(_上穿类型)
            确认根数 = int((当前规则 or {}).get('确认K线数') or 0)
            需要均线确认 = bool((当前规则 or {}).get('需要均线上涨确认', False))
            if _上穿类型 == 'RSI上穿均线' and 需要均线确认 and 确认根数 > 0:
                当前均线 = K线数据.get('RSI_均线_20')
                if 当前均线 is not None and not pd.isna(当前均线):
                    前序均线 = self.MA序列[-确认根数:]
                    if len(前序均线) < 确认根数:
                        self.本根决策['动作原因'] = f'RSI上穿均线等待MA确认，数据不足{len(前序均线)}/{确认根数}根'
                        _上穿阈值 = None
                    elif float(当前均线) <= max(float(x) for x in 前序均线):
                        self.本根决策['动作原因'] = f'RSI上穿均线未通过前{确认根数}根MA最高确认'
                        _上穿阈值 = None

        # 没有新的实际交叉时，旧哨兵只允许向上跟踪。每次实际交叉均为
        # 独立信号事件，即使与当前待成交哨兵属于同一类型，也要形成新的
        # 哨兵价并留在K线记录中。
        _新阈值信号 = bool(
            _上穿阈值 is not None
            and _上穿类型 is not None
            and _上穿类型 != self.哨兵价形成类型
        )
        if (_上穿阈值 is not None
                and (not self.哨兵价已形成 or _新阈值信号 or _本根实际上穿)
                and len(self.价格序列) >= 16):
            # 本根收盘完成后，用包含本根在内的最近15根选定价格计算
            # 下一根使用的反推价；下一根只读取已保存的结果，不再读取
            # 下一根收盘 RSI。
            try:
                _窗口 = list(self.价格序列[-15:])
                if not np.any(np.isnan([x for x in _窗口 if x is not None])):
                    _结果 = 计算RSI反推价(_窗口, _上穿阈值)
                    _反推价 = _结果.get('RSI反推价')
                    if _反推价 is not None:
                        当前收盘 = float(K线数据.get('前复权_收盘', 0) or 0)
                        if 当前收盘 <= 0 or float(_反推价) > 当前收盘 * 2:
                            return
                        self.本根反推价 = _反推价
                        self.本根反推信号类型 = _上穿类型
                        self.本根反推目标RSI = _上穿阈值
                        # 哨兵价的基准必须是上穿发生前已经完成的上一根最高价。
                        # 当前K线最高价只负责后续突破判断，不能参与候选哨兵价形成，
                        # 否则回放中会出现哨兵价直接跳到当前K线最高价的未来数据假象。
                        _候选 = 形成候选(_反推价, self.上一根_最高价)
                        self.待确认哨兵价 = None
                        self.待确认哨兵价类型 = None
                        self.RSI反推价当前 = _候选['RSI反推价']
                        self.上一根突破基准价当前 = _候选['上一根最高价']
                        self.哨兵价当前 = _候选['触发边界']
                        self.最终买入触发价当前 = self.哨兵价当前
                        self.哨兵价已形成 = True
                        self.哨兵价跟踪启用 = True
                        self.哨兵价可执行 = True
                        self.哨兵价已确认可执行 = True
                        self.哨兵价形成类型 = _上穿类型
                        self.哨兵价锁定信号类型 = _上穿类型
                        self.哨兵价形成索引 = 当前索引
                        self.哨兵价本根新形成 = True
                        self.哨兵量价快照 = self._生成哨兵量价快照()
                        self._本根哨兵价来源 = "formed"
            except Exception:
                pass
        
        pass  # 跟踪上移移到 _检查买入 之后执行
    
    def _检查卖出(self, 持仓, K线数据, 当前索引, 股票_code=None):
        """检查持仓是否需要卖出"""
        if (getattr(self, '卖出时机模式', 'intrabar_stop') == 'next_bar_open'
                and 股票_code in getattr(self, '待次根开盘卖出', {})):
            self.本根决策['动作原因'] = '已有待卖单，等待下一根K线开盘执行'
            return
        if self._行情不可交易(K线数据):
            self.本根决策["动作原因"] = "行情缺失、停牌或无成交量，跳过卖出"
            return
        if self._封死跌停(K线数据):
            self.本根决策["动作原因"] = "跌停封死，无可成交买单，跳过卖出"
            return

        # 新买入的持仓从下一根K线开始接受卖出检查，避免同根买卖。
        if 持仓.get('买入时间', -1) >= self.已买入K线数:
            return
        
        不复权收盘 = self.上一根_不复权收盘 or K线数据.get('不复权_收盘', 0)
        if 不复权收盘 <= 0:
            return
        # ★ 修复: 检查持仓是否已被删除
        if 股票_code not in self.当前持仓:
            return

        # 计算当前盈亏
        买入价 = 持仓['买入价']
        预估卖出价 = 不复权收盘 * (1 - self.滑点)
        预估卖出金额 = 持仓['股数'] * 预估卖出价
        预估卖出佣金 = max(预估卖出金额 * self.佣金率, 5)
        预估卖出税费 = 预估卖出金额 * self.印花税率
        预估卖出过户费 = 预估卖出金额 * self.过户费率
        预估净收入 = 预估卖出金额 - 预估卖出佣金 - 预估卖出税费 - 预估卖出过户费
        盈亏比例 = (预估净收入 - 持仓.get('总成本', 持仓['成本'])) / max(持仓.get('总成本', 持仓['成本']), 1)
        
        # 卖出规则只使用上一根已完成K线的指标和持仓状态。
        当前RSI = K线数据.get('_上一根RSI', 50)
        self.交易记录器.更新RSI峰值(当前RSI)
        
        # 当前持仓比例（单股模式下始终=1.0，表示持有全部仓位）
        当前持仓比例 = 1.0
        
        # 检查反推价突破（买入后跟踪哨兵价关卡）
        if len(self.价格序列) >= 15:
            try:
                from 策略引擎.反推因子 import 所有反推候选
                候选列表 = 所有反推候选(
                    self.价格序列[-15:],
                    RSI_MA_上一根=self.上一根_RSI_MA,
                    上一根最高价=self.上一根_最高价,
                )
                当前最高 = K线数据.get('前复权_最高', 0)
                for c in 候选列表:
                    if c['是否有效'] and c['目标价位'] and 当前最高 >= c['目标价位']:
                        self.交易记录器.记录反推价突破(c['目标价位'], c['目标RSI'], c['关卡名'])
            except Exception as error:
                self._记录策略异常("卖出反推突破", error, 当前索引)
        
        # 遍历卖出规则
        前复权最低 = K线数据.get('前复权_最低', 0)
        前复权开盘 = K线数据.get('前复权_开盘', 0)
        self.本根决策["决策记录"]["阶段"] = "卖出检查"
        self.本根决策["决策记录"]["卖出"] = {
            "持仓股票": 股票_code,
            "持有K线数": self.已买入K线数 - 持仓['买入时间'],
            "当前盈亏": 盈亏比例,
            "RSI峰值": 持仓.get('RSI峰值'),
            "当前RSI": 当前RSI,
            "最高价": 持仓.get('最高价'),
            "规则结果": [],
        }
        
        # 因子管理器：卖出前检查 (所有因子默认关闭)
        if self.因子管理器 and self.因子管理器.已启用因子:
            触发列表 = self.因子管理器.卖出前检查(持仓, K线数据, self.全局状态)
            for 触发 in 触发列表:
                if 触发.get("触发卖出", False):
                    self._执行卖出(
                        持仓, 规则={"说明": 触发.get("卖出原因", "因子触发")},
                        盈亏比例=None, K线数据=K线数据,
                        触发价=触发.get("触发价"), 股票代码=股票_code,
                        卖出比例=触发.get("卖出比例", 1.0)
                    )
                    return

        for 规则 in self.卖出规则列表:
            if getattr(self, 'RSI阈值守仓启用', False):
                try:
                    守仓模块 = __import__('6_卖出规则.rsi_threshold_hold', fromlist=['应暂缓'])
                    守仓配置 = getattr(self, 'RSI阈值守仓配置', {})
                    守仓状态 = getattr(self, 'RSI阈值守仓状态', {})
                    暂缓规则 = 守仓配置.get('暂缓卖出规则', ['atr_trailing'])
                    if 守仓模块.应暂缓(守仓状态, 规则['名称'], 暂缓规则):
                        阈值名 = 守仓状态.get('阈值名称', 'RSI守仓阈值')
                        当前值 = 守仓状态.get('当前RSI', 当前RSI)
                        原因 = f"RSI阈值守仓：RSI({当前值:.2f})未下穿{阈值名}，暂缓{规则['名称']}"
                        self.本根决策["卖出检查"].append({
                            "规则": 规则['名称'], "满足": False, "原因": 原因,
                        })
                        self.本根决策["决策记录"]["卖出"]["规则结果"].append({
                            "规则": 规则['名称'], "触发": False, "原因": 原因,
                        })
                        continue
                except Exception as e:
                    setattr(self, 'RSI阈值守仓状态', {"错误": str(e)})
            try:
                结果 = 规则['模块'].检查(
                    持仓盈亏比例=盈亏比例,
                    当前ATR=self.上一根_ATR if self.上一根_ATR is not None else K线数据.get('ATR_14', 0),
                    买入价=买入价,
                    最高价=持仓.get('最高价'),
                    前复权买入价=持仓.get('前复权成交价', 持仓.get('前复权买入价')),
                    当前持仓比例=当前持仓比例,
                    RSI峰值=持仓.get('RSI峰值'),
                    当前RSI=当前RSI,
                    上一根最低价RSI=K线数据.get('_上一根最低价RSI'),
                    当前最低价RSI=K线数据.get('RSI_最低价'),
                    持有K线数=self.已买入K线数 - 持仓['买入时间'],
                    MA斜率=self._获取MA斜率(),
                    有底背离=self.有底背离,
                    有顶背离=self.有顶背离,
                    **{k: v for k, v in 规则.get('配置', {}).items() 
                       if k not in ['名称', '英文标识', '启用', '检查顺序', '说明']},
                )
            except Exception as e:
                self.本根决策["卖出检查"].append({
                    "规则": 规则['名称'], "满足": False,
                    "原因": f"规则执行异常: {e}"
                })
                continue

            self.本根决策["卖出检查"].append({
                "规则": 规则['名称'],
                "满足": bool(结果.get('触发')),
                "原因": 结果.get('原因', '未触发'),
                "触发价": 结果.get('止损价'),
            })
            self.本根决策["决策记录"]["卖出"]["规则结果"].append({
                "规则": 规则['名称'],
                "触发": bool(结果.get('触发')),
                "原因": 结果.get('原因', '未触发'),
                "触发价": 结果.get('止损价'),
            })
            
            if not 结果.get('触发'):
                continue

            # CMSF 等扩展因子只能过滤已由原卖出规则确认的信号，绝不直接
            # 新建订单；全部关闭时该分支保持原策略行为。
            if self.因子管理器 and self.因子管理器.已启用因子:
                卖出过滤 = self.因子管理器.卖出信号过滤(
                    持仓, K线数据, self.全局状态, 规则
                )
                self.本根决策["决策记录"]["卖出"].setdefault("扩展因子过滤", {})[
                    规则.get('名称', '未命名规则')
                ] = 卖出过滤.get("明细", {})
                if not 卖出过滤.get("允许卖出", True):
                    self.本根决策["卖出检查"][-1]["满足"] = False
                    self.本根决策["卖出检查"][-1]["原因"] = (
                        "扩展因子暂缓: " + 卖出过滤.get("说明", "未放行")
                    )
                    self.本根决策["决策记录"]["卖出"]["规则结果"][-1].update({
                        "触发": False,
                        "原因": self.本根决策["卖出检查"][-1]["原因"],
                    })
                    continue
            
            # 计算触发价（对称于买入的哨兵价）
            触发价 = self._计算卖出触发价(结果, K线数据)
            
            if 触发价 is not None:
                # 价格跌破型：当前最低价必须跌破触发价才执行
                if 前复权最低 > 触发价:
                    continue

            # ATR 跟踪止盈只在当前K线形成更低的低点时确认平仓。
            # 当前低点未跌破上一根低点时，视为回撤未确认；确认后使用
            # 上一根最低价作为执行线，避免直接用当前K线的极端低点成交。
            if (规则.get('名称') == 'atr_take_profit'
                    and 结果.get('价格确认', True)):
                上一根最低 = self.上一根_最低价
                try:
                    当前最低值 = float(前复权最低)
                    上一根最低值 = float(上一根最低)
                except (TypeError, ValueError):
                    continue
                if 当前最低值 >= 上一根最低值:
                    self.本根决策["卖出检查"][-1]["满足"] = False
                    self.本根决策["卖出检查"][-1]["原因"] = (
                        "ATR止盈价格确认未通过：当前K线最低价未低于上一根最低价"
                    )
                    self.本根决策["决策记录"]["卖出"]["规则结果"][-1].update({
                        "触发": False,
                        "原因": "ATR止盈价格确认未通过：当前K线最低价未低于上一根最低价",
                    })
                    continue
                触发价 = 上一根最低值

            # “ATR跟踪止盈（仅盈利触发）”不仅要在检查时盈利，实际
            # 触发线成交后也必须覆盖持仓成本和卖出费用，不能因跟踪线
            # 低于均价而把浮盈信号执行成亏损卖出。
            if 规则.get('名称') == 'atr_take_profit' and 触发价 is not None:
                try:
                    前复权执行价 = min(float(前复权开盘), float(触发价))
                    不复权开盘 = float(K线数据.get('不复权_开盘', 0) or 0)
                    前复权开盘值 = float(前复权开盘 or 0)
                    预估卖出价 = (
                        前复权执行价 * 不复权开盘 / 前复权开盘值
                        * (1 - self.滑点)
                    )
                    预估金额 = 预估卖出价 * float(持仓.get('股数', 0) or 0)
                    预估费用 = (
                        max(预估金额 * self.佣金率, 5)
                        + 预估金额 * self.印花税率
                        + 预估金额 * self.过户费率
                    )
                    预估净收入 = 预估金额 - 预估费用
                    if 预估净收入 <= float(持仓.get('总成本', 持仓.get('成本', 0)) or 0):
                        self.本根决策["卖出检查"][-1]["满足"] = False
                        self.本根决策["卖出检查"][-1]["原因"] = "ATR止盈触发线低于含费用成本，继续持有"
                        self.本根决策["决策记录"]["卖出"]["规则结果"][-1]["触发"] = False
                        self.本根决策["决策记录"]["卖出"]["规则结果"][-1]["原因"] = "ATR止盈触发线低于含费用成本，继续持有"
                        continue
                except (TypeError, ValueError, ZeroDivisionError):
                    continue
            
            if self.卖出时机模式 == 'next_bar_open':
                self.待次根开盘卖出[股票_code] = {
                    '规则': 规则,
                    '触发价': 触发价,
                    '卖出比例': 结果.get('卖出比例', 1.0),
                    '盈亏比例': 盈亏比例,
                    '形成索引': 当前索引,
                }
                self.本根决策['最终动作'] = '待卖出'
                self.本根决策['动作原因'] = '本根触发，下一根K线开盘执行'
                self.本根决策['决策记录']['阶段'] = '卖出待执行'
                self.本根决策['决策记录']['卖出'].update({
                    '结果': '待成交',
                    '执行方式': '下一根K线开盘',
                    '执行触发价': 触发价,
                })
                break

            # 执行卖出（用触发价-滑点成交）
            已卖出 = self._执行卖出(
                持仓, 规则, 盈亏比例, K线数据,
                触发价=触发价, 股票代码=股票_code,
                卖出比例=结果.get('卖出比例', 1.0)
            )
            if 已卖出:
                self.本根决策["最终动作"] = "卖出"
                self.本根决策["动作原因"] = 结果.get('原因', 规则.get('说明', '卖出规则触发'))
                self.本根决策["决策记录"]["阶段"] = "卖出成交"
                self.本根决策["决策记录"]["卖出"]["结果"] = "成交"
                self.本根决策["决策记录"]["卖出"]["执行触发价"] = 触发价
                break

    def _检查加仓(self, 持仓, K线数据, 当前索引, 股票_code=None):
        """检查已有持仓是否触发加仓（扩展因子：加仓前检查）。"""
        触发列表 = []
        if not 持仓 or not self.因子管理器 or not self.因子管理器.已启用因子:
            return
        if self._行情不可交易(K线数据):
            return
        if self.涨停不买 and self._封死涨停(K线数据):
            return

        实际代码 = 股票_code if 股票_code is not None else K线数据.get('股票代码', '600519')
        if 实际代码 not in self.当前持仓:
            return
        self.全局状态["当前索引"] = 当前索引
        self.全局状态["当前持仓"] = self.当前持仓

        # 首笔开仓发生在本根时，禁止网格在同一根K线立即再加仓。
        # 网格基准最高价、当根最低价和扩展因子状态都应从下一根已完成
        # K线开始计算，否则会出现“RSI首笔买入 + L1”同根连续成交。
        # 这也保持了“同一天可以交易，但不能同一根K线重复买入”的规则。
        if int(持仓.get('买入时间', -1) or -1) >= int(self.已买入K线数):
            self.本根决策.setdefault('决策记录', {}).setdefault('买入', {}).update({
                '加仓检查': '跳过',
                '加仓拦截原因': '首笔开仓发生在本根，网格从下一根K线开始计算',
            })
            return

        # 网格触发先累计为待确认状态；严格预挂模式下，后续K线突破已有
        # 哨兵价才允许成交，不要求重新出现 RSI 信号。
        本根新信号 = getattr(self, '本根反推信号类型', None)
        本根有新信号 = bool(getattr(self, '哨兵价本根新形成', False) and 本根新信号)
        待加仓股数 = int(持仓.get('网格_待加仓股数', 0) or 0)
        待加仓金额 = float(持仓.get('网格_待加仓金额', 0.0) or 0.0)
        try:
            待单形成索引 = int(持仓.get('网格_待单形成索引'))
        except (TypeError, ValueError):
            待单形成索引 = None
        # 网格回撤只形成待确认状态；必须在此前已经形成待单，之后再出现
        # 新哨兵价并通过买入因子，不能在下一根开盘直接把网格单成交。
        已有待确认网格 = bool(
            (待加仓股数 > 0 or 待加仓金额 > 0)
            and 待单形成索引 is not None
            and 待单形成索引 < 当前索引
        )
        严格网格 = self.网格加仓时机模式 == STRICT_PRECOMPUTED
        网格哨兵突破 = False
        if 严格网格 and 已有待确认网格 and self.哨兵价当前 is not None:
            try:
                网格哨兵突破 = float(K线数据.get('前复权_最高', 0)) >= float(self.哨兵价当前)
            except (TypeError, ValueError):
                网格哨兵突破 = False

        # 加仓也要满足“买入侧防护”：过滤因子 + 扩展因子买入前检查
        信号类型 = 本根新信号 if 本根有新信号 else (持仓.get('信号类型') or '')
        try:
            信号质量分 = float(持仓.get('信号质量分', self.信号质量对照.get(信号类型, 0.5)) or 0.5)
        except (TypeError, ValueError):
            信号质量分 = 0.5

        if 本根有新信号:
            过滤状态 = {
                '信号质量分': 信号质量分,
                'MA序列': self.MA序列,
                '连续亏损次数': self.连续亏损次数,
                '冷却期剩余K线': self.冷却期剩余K线,
                '有底背离': self.有底背离,
                '有顶背离': self.有顶背离,
                '已有持仓': True,
            }
            过滤状态.update(getattr(self, '过滤运行状态', {}))
            过滤状态['哨兵量价快照'] = getattr(self, '哨兵量价快照', {})
            try:
                过滤结果 = self._检查过滤因子(信号类型, K线数据, 过滤状态)
            except Exception:
                过滤结果 = {"允许买入": True}
            if not 过滤结果.get('允许买入', True):
                return

            try:
                当前持仓市值 = sum(
                    p.get('股数', 0) * (K线数据.get('不复权_开盘', 0) or 0)
                    for p in self.当前持仓.values()
                )
                self.全局状态.update({
                    "信号质量": 信号质量分,
                    "总权益": self.当前现金 + 当前持仓市值,
                    "当前持仓": self.当前持仓,
                    "当前现金": self.当前现金,
                })
                扩展买入结果 = self.因子管理器.买入前检查(K线数据, self.全局状态)
                if not 扩展买入结果.get("允许买入", True):
                    return
            except Exception:
                pass
        # 网格回撤本身就是触发条件，不应等待新的 RSI 信号才检查。
        # 严格模式的成交确认在后面单独要求“先有待单、后有哨兵突破”。
        if not 触发列表:
            触发列表 = self.因子管理器.加仓前检查(持仓, K线数据, self.全局状态)
        # 已有待加仓单时，严格模式只要本根突破预挂哨兵价即可执行，
        # 不再要求重新出现 RSI 信号。首次在本根同时回撤和突破时，
        # 因 OHLC 无法判断盘中先后，只保留待单，下一根再确认。
        if (严格网格 and not 触发列表 and 已有待确认网格 and 网格哨兵突破 and
                (int(持仓.get('网格_待加仓股数', 0) or 0) > 0
                 or float(持仓.get('网格_待加仓金额', 0.0) or 0.0) > 0)):
            触发列表 = [{
                '触发加仓': True,
                '触发价': self.哨兵价当前,
                '加仓股数': int(持仓.get('网格_待加仓股数', 0) or 0),
                '加仓金额': float(持仓.get('网格_待加仓金额', 0.0) or 0.0),
                '网格层级': max(list(持仓.get('网格_待加仓层级', []) or [1])),
                '因子': 'grid_addon',
                '_仅执行待单': True,
                '_预挂哨兵突破': True,
            }]
        if not 触发列表:
            if (持仓.get('网格_待加仓股数', 0)
                    or 持仓.get('网格_待加仓金额', 0.0)):
                self.本根决策.setdefault('决策记录', {}).setdefault('买入', {}).update({
                    '加仓检查': '待成交',
                    '加仓拦截原因': '已满足网格回撤，等待新的哨兵价和买入因子确认',
                })
            return

        # 默认同一根K线最多执行一次加仓（除非因子明确允许）
        for 触发 in 触发列表:
            if not 触发.get("触发加仓", False):
                continue
            try:
                触发价 = float(触发.get("触发价")) if 触发.get("触发价") is not None else None
            except (TypeError, ValueError):
                触发价 = None
            try:
                加仓股数 = int(float(触发.get("加仓股数"))) if 触发.get("加仓股数") is not None else None
            except (TypeError, ValueError):
                加仓股数 = None
            try:
                加仓金额 = float(触发.get("加仓金额")) if 触发.get("加仓金额") is not None else None
            except (TypeError, ValueError):
                加仓金额 = None
            # 网格仓位只由首笔实际成交数量及层级决定；首次开仓的信号
            # 资金系数只用于首次开仓，不能缩放后续网格加仓。
            生命周期预算 = (
                触发.get("网格模式") == "lifecycle_budget"
                or ((加仓金额 or 0) > 0 and (加仓股数 or 0) <= 0)
            )
            if (not 触发价 or (生命周期预算 and (加仓金额 is None or 加仓金额 <= 0))
                    or (not 生命周期预算 and (not 加仓股数 or 加仓股数 < 100))):
                continue

            仅执行待单 = bool(触发.get('_仅执行待单', False))
            层级 = int(触发.get('网格层级', 持仓.get('网格_已触发次数', 0) + 1) or 0)
            待层级 = list(持仓.get('网格_待加仓层级', []) or [])
            if not 仅执行待单:
                if 层级 not in 待层级:
                    待层级.append(层级)
                持仓['网格_已触发次数'] = max(int(持仓.get('网格_已触发次数', 0) or 0), 层级)
                持仓['网格_待加仓层级'] = sorted(待层级)
                if 生命周期预算:
                    持仓['网格_待加仓金额'] = float(
                        持仓.get('网格_待加仓金额', 0.0) or 0.0
                    ) + float(加仓金额 or 0.0)
                else:
                    持仓['网格_待加仓股数'] = (
                        int(持仓.get('网格_待加仓股数', 0) or 0) + int(加仓股数 or 0)
                    )
                if 持仓.get('网格_待单形成索引') is None:
                    持仓['网格_待单形成索引'] = 当前索引
            下一根开盘执行 = False
            允许本根执行 = bool(
                本根有新信号
                or (严格网格 and 已有待确认网格 and 网格哨兵突破)
            )
            if not 允许本根执行:
                self.本根决策.setdefault('决策记录', {}).setdefault('买入', {}).update({
                    '加仓检查': '待成交',
                    '加仓拦截原因': '网格回撤已触发，等待回撤后的哨兵价突破',
                    '待加仓层级': ' + '.join(f'L{x}' for x in 持仓['网格_待加仓层级']),
                    '待加仓股数': 持仓['网格_待加仓股数'],
                })
                continue

            # 最终成交前再次校验，防止任何待单/因子路径绕过“本根新哨兵”条件。
            # 网格回撤只能产生待确认数量，不能单独调用成交模型。
            if (严格网格 and not 网格哨兵突破) or (
                    not 严格网格 and not getattr(self, '哨兵价本根新形成', False)):
                self.本根决策.setdefault('决策记录', {}).setdefault('买入', {}).update({
                    '加仓检查': '待成交',
                    '加仓拦截原因': '网格回撤已满足，但本根未突破有效哨兵价',
                })
                continue

            新规则 = self._获取买入规则(
                本根新信号 or 持仓.get('信号类型')
            ) or (self.买入规则列表[0] if self.买入规则列表 else {})
            if not 新规则:
                continue
            累计加仓股数 = int(持仓.get('网格_待加仓股数', 0) or 0)
            累计加仓金额 = float(持仓.get('网格_待加仓金额', 0.0) or 0.0)
            待成交层级 = list(持仓.get('网格_待加仓层级', []) or [])
            if 累计加仓股数 <= 0:
                if 累计加仓金额 <= 0:
                    continue

            当前RSI = K线数据.get('_上一根RSI', 50)
            层级标识 = '+'.join(f'L{x}' for x in 待成交层级) or f'L{层级}'
            # 合并成交必须使用本根新买入信号的实际触发价，不使用历史网格触发价。
            成交哨兵价 = (
                K线数据.get('前复权_开盘') if 下一根开盘执行
                else self.哨兵价当前 if 严格网格 and self.哨兵价当前 else
                (self.哨兵价当前 if 本根有新信号 and self.哨兵价当前 else 触发价)
            )
            成交前股数 = int(持仓.get('股数', 0) or 0)
            已加仓 = self._执行买入(
                规则=None, K线数据=K线数据, 当前索引=当前索引,
                当前RSI=当前RSI,
                哨兵价=成交哨兵价,
                信号类型=f"网格加仓 {层级标识}",
                信号质量分=信号质量分,
                建议仓位=None,
                按开盘成交=下一根开盘执行,
                指定股数=None if 累计加仓金额 > 0 else 累计加仓股数,
                指定金额=累计加仓金额 if 累计加仓金额 > 0 else None,
                成交模式="normal" if (下一根开盘执行 or 严格网格) else "pullback",
                最大成交价=持仓.get('网格_首次买入价', 持仓.get('买入价')),
            )
            if 已加仓:
                实际加仓股数 = max(0, int(持仓.get('股数', 0) or 0) - 成交前股数)
                持仓['网格_已加仓次数'] = int(持仓.get('网格_已触发次数', 0) or 0)
                持仓['网格_待加仓股数'] = 0
                持仓['网格_待加仓金额'] = 0.0
                持仓['网格_待加仓层级'] = []
                持仓['网格_待单形成索引'] = None
                self.交易记录器.更新交易记录(
                    self.交易记录器.买入序号, '买入',
                    信号类型=f"网格加仓 {层级标识}",
                    网格级别=max(待成交层级) if 待成交层级 else 层级,
                    网格层级标识=层级标识,
                    加仓后总持仓=持仓.get('股数'),
                )
                self.本根决策["最终动作"] = "加仓"
                self.本根决策["动作原因"] = f"网格累计加仓 {层级标识}，本次合并成交{实际加仓股数}股"
                self.本根决策["决策记录"]["阶段"] = "加仓成交"
                self.本根决策.setdefault("决策记录", {}).setdefault("买入", {}).update({
                    "加仓原因": self.本根决策["动作原因"],
                    "加仓触发价": 触发价,
                    "加仓股数": 实际加仓股数,
                    "加仓金额": 累计加仓金额 if 累计加仓金额 > 0 else None,
                    "加仓因子": 触发.get("因子"),
                    "买入条件重新确认": bool(本根有新信号),
                    "重新确认信号": 本根新信号,
                    "网格层级": 层级标识,
                    "执行方式": "下一根K线开盘" if 下一根开盘执行 else "买入信号确认",
                })
            if 已加仓 and not bool(触发.get("允许同根多次加仓", False)):
                break

    def _行情不可交易(self, K线数据):
        """统一拦截缺失、停牌和无成交量K线。"""
        价格列 = ('前复权_开盘', '前复权_最高', '前复权_最低', '前复权_收盘',
                  '不复权_开盘', '不复权_最高', '不复权_最低', '不复权_收盘')
        for 列 in 价格列:
            值 = K线数据.get(列)
            if 值 is None or pd.isna(值) or float(值) <= 0:
                return True
        成交量 = K线数据.get('成交量', K线数据.get('不复权_成交量'))
        return 成交量 is None or pd.isna(成交量) or float(成交量) <= 0

    def _涨跌停价(self, K线数据):
        """按上一根不复权收盘价估算本根涨跌停价。"""
        上一收盘 = self.上一根_不复权收盘
        if 上一收盘 is None or pd.isna(上一收盘) or float(上一收盘) <= 0:
            return None, None
        上一收盘 = float(上一收盘)
        比例 = self._获取涨跌停比例(K线数据)
        return 上一收盘 * (1 + 比例), 上一收盘 * (1 - 比例)

    def _获取涨跌停比例(self, K线数据):
        """按板块和日期确定涨跌停比例，配置值作为主板默认值。"""
        股票代码 = str(K线数据.get('股票代码', '')).strip().upper()
        for prefix in ('SH_', 'SZ_', 'BJ_'):
            if 股票代码.startswith(prefix):
                股票代码 = 股票代码[len(prefix):]
                break
        日期 = str(K线数据.get('日期', ''))[:10]
        # 科创板 688/689 统一执行 20% 涨跌停规则。
        if 股票代码.startswith(('688', '689')):
            return 0.20
        if 股票代码.startswith(('300', '301')) and 日期 >= '2020-08-24':
            return 0.20
        if 股票代码.startswith(('4', '8', '9')):
            return 0.30
        return float(getattr(self, '涨跌停比例', 0.10))

    @staticmethod
    def _最低交易单位(股票代码):
        """返回当前板块的整手单位，买入和部分卖出共用。"""
        code = str(股票代码 or '').strip().upper()
        for prefix in ('SH_', 'SZ_', 'BJ_'):
            if code.startswith(prefix):
                code = code[len(prefix):]
        if code.startswith(('688', '689')):
            return 200
        if code.startswith(('4', '8', '9')):
            return 300
        return 100

    @classmethod
    def _计算卖出股数(cls, 股票代码, 原股数, 卖出比例):
        """按板块单位取整；不足一手时清空剩余持仓，避免非法零碎卖出。"""
        原股数 = max(0, int(原股数 or 0))
        比例 = min(max(float(卖出比例 or 1.0), 0.0), 1.0)
        请求股数 = int(原股数 * 比例)
        if 请求股数 <= 0:
            return 0
        if 请求股数 >= 原股数:
            return 原股数
        单位 = cls._最低交易单位(股票代码)
        取整股数 = (请求股数 // 单位) * 单位
        return 取整股数 if 取整股数 >= 单位 else 原股数

    def _封死涨停(self, K线数据):
        """当根开高低收均在涨停价，视为封死涨停，不能追买。"""
        涨停价, _ = self._涨跌停价(K线数据)
        if 涨停价 is None:
            return False
        价格 = [K线数据.get(列) for 列 in ('不复权_开盘', '不复权_最高', '不复权_最低', '不复权_收盘')]
        if any(值 is None or pd.isna(值) for 值 in 价格):
            return False
        容差 = max(0.011, 涨停价 * 0.0005)
        return all(abs(float(值) - 涨停价) <= 容差 for 值 in 价格)

    def _封死跌停(self, K线数据):
        """当根开高低收均在跌停价，视为封死跌停，不能卖出。"""
        _, 跌停价 = self._涨跌停价(K线数据)
        if 跌停价 is None:
            return False
        价格 = [K线数据.get(列) for 列 in ('不复权_开盘', '不复权_最高', '不复权_最低', '不复权_收盘')]
        if any(值 is None or pd.isna(值) for 值 in 价格):
            return False
        容差 = max(0.011, 跌停价 * 0.0005)
        return all(abs(float(值) - 跌停价) <= 容差 for 值 in 价格)
    
    def _计算卖出触发价(self, 规则结果, K线数据=None):
        """从卖出规则结果中提取触发价格（对称于买入哨兵价）"""
        from 策略引擎.站岗价因子 import 计算站岗价
        
        # 1. 硬止损 → 直接返回止损价
        止损价 = 规则结果.get('止损价')
        if 止损价 is not None:
            return 止损价
        
        # 2. 站岗价因子 → 计算RSI回落阈值对应的价格防线
        RSI峰值 = 规则结果.get('RSI峰值')
        回落阈值 = 规则结果.get('回落阈值')
        if RSI峰值 is not None and 回落阈值 is not None:
            if len(self.价格序列) >= 15:
                try:
                    当前RSI = K线数据.get('_上一根RSI', 50) if K线数据 is not None else None
                    当前最低 = self.上一根_最低价
                    结果 = 计算站岗价(
                            self.价格序列[-15:],
                            当前RSI=当前RSI,
                            RSI峰值=RSI峰值,
                            回落阈值=回落阈值,
                            上根最低价=self.上一根_最低价,
                            当前最低价=当前最低,
                    )
                    return 结果.get('站岗价')
                except Exception as error:
                    self._记录策略异常("站岗价计算", error, None)
        
        # 3. 其他规则（时间退出等）→ 没有价格线
        return None
    
    
    def _获取MA斜率(self):
        """计算最近5根K线的RSI_MA斜率，用于ATR动态调整"""
        if len(self.RSI_MA历史) >= 6:
            return self.RSI_MA历史[-1] - self.RSI_MA历史[-6]
        return None
    def _执行卖出(self, 持仓, 规则, 盈亏比例, K线数据, 触发价=None, 股票代码='600519', 卖出比例=1.0):
        """执行卖出（对称于买入：价格跌破触发价-滑点卖出）"""
        持有K线数 = self.已买入K线数 - 持仓['买入时间']
        
        # 计算卖出执行价（对称于买入的 max(开盘, 哨兵价) + 滑点）
        不复权开盘 = K线数据.get('不复权_开盘', 0)
        前复权开盘 = K线数据.get('前复权_开盘', 0)
        
        if 触发价 is not None and 触发价 > 0 and 前复权开盘 > 0:
            # 有价格线：按 min(开盘, 触发价) × (1 - 滑点) 成交
            前复权执行价 = min(前复权开盘, 触发价)
            卖出价 = 前复权执行价 * (不复权开盘 / 前复权开盘) * (1 - self.滑点)
        else:
            # 无价格线（时间退出等）：按开盘价 × (1 - 滑点）
            卖出价 = 不复权开盘 * (1 - self.滑点) if 不复权开盘 > 0 else 0

        # 实际不复权成交价按股票报价精度保留两位小数；复权触发价仍
        # 只用于前面的触发判断，不作为账面成交价。
        卖出价 = round(float(卖出价), 2)
        
        if 卖出价 <= 0:
            return False
        
        原股数 = int(持仓['股数'])
        卖出比例 = min(max(float(卖出比例 or 1.0), 0.0), 1.0)
        卖出股数 = self._计算卖出股数(股票代码, 原股数, 卖出比例)
        if 卖出股数 <= 0:
            return False
        卖出金额 = 卖出股数 * 卖出价
        
        # 交易费用: 佣金(万2.5, 最低5元) + 印花税(万5) + 过户费(万0.1)
        卖出佣金 = max(卖出金额 * self.佣金率, 5)
        卖出印花税 = 卖出金额 * self.印花税率
        卖出过户费 = 卖出金额 * self.过户费率
        卖出费用 = 卖出佣金 + 卖出印花税 + 卖出过户费
        卖出净金额 = 卖出金额 - 卖出费用
        本次成本 = 持仓.get('总成本', 持仓['成本']) * 卖出股数 / 原股数
        实际盈亏比例 = (卖出净金额 - 本次成本) / max(本次成本, 1)
        
        self.当前现金 += 卖出净金额
        # ★ 修复: 安全删除持仓，防止键值不匹配
        实际代码 = 股票代码 if 股票代码 is not None else K线数据.get('股票代码', '600519')
        if 实际代码 in self.当前持仓:
            if 卖出股数 >= 原股数:
                del self.当前持仓[实际代码]
            else:
                持仓['股数'] = 原股数 - 卖出股数
                持仓['成本'] *= 持仓['股数'] / 原股数
                持仓['总成本'] *= 持仓['股数'] / 原股数
        if 实际盈亏比例 < 0:
            self.连续亏损次数 += 1
            if self.连续亏损次数 >= 3:  # 连续亏3次暂停
                self.冷却期剩余K线 = 10  # 暂停10根K线
        else:
            self.连续亏损次数 = 0  # 盈利一次就清零
        
        # 记录交易
        self.交易记录器.记录卖出(
            卖出价=卖出价,
            卖出原因=规则['说明'],
            盈亏比例=实际盈亏比例,
            持有K线数=持有K线数,
            RSI峰值=持仓.get('RSI峰值'),
            日期=K线数据.get('日期', ''),
            时间=str(getattr(K线数据, 'name', '') or ''),
            仓位=本次成本,
            成交数量=卖出股数,
            持仓组ID=持仓.get('持仓组ID'),
        )
        self.本根决策["决策记录"]["卖出"].update({
            "成交价": 卖出价,
            "成交数量": 卖出股数,
            "成交金额": 卖出金额,
            "交易费用": 卖出费用,
            "实际盈亏比例": 实际盈亏比例,
        })
        self.交易记录器.更新交易记录(
            self.交易记录器.买入序号, '卖出',
            卖出决策记录=self.本根决策.get('决策记录', {}),
            交易费用=卖出费用,
            卖出净金额=卖出净金额,
        )
        self.交易记录器.更新交易记录(
            self.交易记录器.买入序号, '买入',
            卖出决策记录=self.本根决策.get('决策记录', {}),
        )
        self._记录账户审批(
            类型="卖出", 结果="实际成交", 原因=规则.get('说明', '卖出规则触发'),
            请求股数=卖出股数, 成交股数=卖出股数, 成交价=卖出价,
            交易费用=卖出费用, 成交净额=卖出净金额, 盈亏比例=实际盈亏比例,
            网格层级=int(持仓.get('网格_已加仓次数', 0) or 0),
            时间=str(getattr(K线数据, 'name', K线数据.get('完整时间', K线数据.get('日期', '')))),
        )
        return True
    
    def 获取结果(self, 估值K线=None):
        """获取最终结果"""
        持仓市值 = 0.0
        if 估值K线 is not None:
            收盘价 = 估值K线.get('不复权_收盘', 0)
            持仓市值 = sum(p.get('股数', 0) * 收盘价 for p in self.当前持仓.values())
        return {
            "交易明细": self.交易记录器.导出明细(),
            "持仓过程": self.交易记录器.导出持仓过程(),
            "最终现金": self.当前现金,
            "期末持仓市值": 持仓市值,
            "最终权益": self.当前现金 + 持仓市值,
            "剩余持仓": len(self.当前持仓),
            "策略异常记录": list(getattr(self, "策略异常记录", [])),
            "策略异常计数": dict(getattr(self, "策略异常计数", {})),
            "卖出时机模式": self.卖出时机模式,
        }


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    print("=" * 40)
    print("规则执行器 — 集成测试")
    print("=" * 40)
    
    from 数据模块.股票加载器 import 加载股票
    
    数据 = 加载股票("600519", "双价格合并").head(200)
    
    if 数据 is not None:
        配置目录 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '1_策略配置')
        执行器 = 规则执行器(配置目录)
        
        for i in range(len(数据)):
            行 = 数据.iloc[i]
            # 添加上一根RSI
            if i > 0:
                行['_上一根RSI'] = 数据.iloc[i-1].get('RSI_14', 50)
            执行器.每根K线处理(行, i)
        
        结果 = 执行器.获取结果()
        print(f"\n回测结果:")
        print(f"  处理K线: {len(数据)} 根")
        print(f"  交易次数: {len(结果['交易明细'])} 笔")
        print(f"  最终现金: {结果['最终现金']:.0f}")
        print(f"  剩余持仓: {结果['剩余持仓']}")
        
        if len(结果['交易明细']) > 0:
            print(f"\n交易明细:")
            print(结果['交易明细'][['类型', '信号类型', '买入价', '卖出原因', '盈亏比例']].to_string())
    
    print("\n✅ 规则执行器集成测试完成")
