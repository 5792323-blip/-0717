# rsi_neutral_zone_filter.py — RSI中性区过滤因子
# 功能: RSI位于中性区间时不交易

def 检查(哨兵价类型, K线数据, 状态, 配置):
    """
    在 RSI 位于指定中性区间时拦截买入。

    配置项:
        中性下限: 默认 42
        中性上限: 默认 58
        适用信号: 空列表表示全部信号都检查
        历史不足时放行: 数据不足时是否默认放行
    """
    适用信号 = 配置.get("适用信号", []) or []
    if 适用信号 and 哨兵价类型 not in 适用信号:
        return {"通过": True, "原因": f"信号{哨兵价类型}不在适用列表, 通过"}

    当前RSI = K线数据.get("RSI_14", None)
    if 当前RSI is None:
        return {
            "通过": bool(配置.get("历史不足时放行", True)),
            "原因": "RSI数据不足, 放行" if 配置.get("历史不足时放行", True) else "RSI数据不足, 拦截",
        }

    try:
        当前RSI = float(当前RSI)
    except (TypeError, ValueError):
        return {"通过": bool(配置.get("历史不足时放行", True)), "原因": "RSI无效, 参考历史不足策略"}

    下限 = float(配置.get("中性下限", 42))
    上限 = float(配置.get("中性上限", 58))
    if 下限 > 上限:
        下限, 上限 = 上限, 下限

    if 下限 <= 当前RSI <= 上限:
        return {
            "通过": False,
            "原因": f"RSI={当前RSI:.1f}位于中性区[{下限:.0f},{上限:.0f}], 拦截",
        }

    return {"通过": True, "原因": f"RSI={当前RSI:.1f}, 通过"}

