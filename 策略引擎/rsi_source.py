"""RSI价格源组装器：同时计算三条RSI，再选一条接入原策略。"""

from 策略引擎 import rsi_close, rsi_high, rsi_low
from 策略引擎.rsi_ma import 计算RSI均线


模块对照 = {
    "high": rsi_high,
    "close": rsi_close,
    "low": rsi_low,
}
列名对照 = {
    "high": "RSI_最高价",
    "close": "RSI_收盘价",
    "low": "RSI_最低价",
}


def 准备RSI指标(数据, 价格源="close", RSI周期=14, 均线周期=20):
    """
    返回新DataFrame，保留三条RSI并把所选序列映射到旧接口。

    旧代码继续读取 ``RSI_14`` 和 ``RSI_均线_20``，因此无需让
    每个买卖规则知道当前选择了哪一种价格源。
    """
    价格源 = str(价格源 or "close").lower()
    if 价格源 not in 模块对照:
        raise ValueError(f"不支持的RSI价格源: {价格源}")
    结果 = 数据.copy()
    for 标识, 模块 in 模块对照.items():
        结果[列名对照[标识]] = 模块.计算(结果, 周期=int(RSI周期)).values
    结果["RSI_14"] = 结果[列名对照[价格源]]
    结果["RSI_均线_20"] = 计算RSI均线(结果["RSI_14"], 周期=int(均线周期))
    结果["RSI_价格源"] = 价格源
    return 结果
