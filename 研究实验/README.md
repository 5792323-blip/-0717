# 研究实验

这些程序用于训练期研究，不会自动成为正式策略。

| 程序 | 功能 |
|---|---|
| `module_ablation_backtest.py` | 单独打开/关闭一个模块，比较边际效果。 |
| `signal_ablation_experiment.py` | 逐一关闭4种RSI买入信号。 |
| `entry_optimization_experiment.py` | 买入结构、成交额和分段稳健性实验。 |
| `exit_rule_experiment.py` | 硬止损实验及公共配置复制工具。 |
| `atr_exit_experiment.py` | ATR跟踪退出倍数实验。 |
| `stagnation_exit_experiment.py` | 无效交易退出实验。 |
| `market_regime_experiment.py` | 沪深300市场状态过滤实验。 |
| `volatility_regime_experiment.py` | 波动率状态过滤实验。 |
| `risk_on_filter_experiment.py` | 长期均线风险开关实验。 |
| `robust_signal_walkforward.py` | 年度、横截面分桶和滚动稳健训练。 |
| `shared_portfolio_ablation.py` | 两套信号在共享资金账户中的消融。 |
| `cross_sectional_baseline_experiment.py` | 横截面共享资金基线。 |
| `cross_sectional_turnover_experiment.py` | 换手缓冲、分批轮换和持仓分散实验。 |
| `cross_sectional_risk_control_experiment.py` | 横截面组合的大盘风险控制实验。 |

运行方式统一使用模块形式，例如：

```bash
python3 -m 研究实验.module_ablation_backtest --help
```
