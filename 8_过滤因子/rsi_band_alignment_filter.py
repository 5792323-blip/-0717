# rsi_band_alignment_filter.py — RSI区间对齐过滤因子
# 功能: 模仿TB里“低位信号只在低区间放行，高位信号只在高区间放行”的门槛

def 检查(哨兵价类型, K线数据, 状态, 配置):
    """
    当 RSI 落在中性区时，只有和区间方向一致的信号才放行。

    低位信号默认: RSI上穿20 / RSI上穿30 / RSI上穿均线
    高位信号默认: RSI上穿70 / RSI上穿80
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

    低位信号 = set(配置.get("低位信号", ["RSI上穿20", "RSI上穿30", "RSI上穿均线"]))
    高位信号 = set(配置.get("高位信号", ["RSI上穿70", "RSI上穿80"]))

    if 当前RSI < 下限:
        if 哨兵价类型 in 低位信号:
            return {"通过": True, "原因": f"RSI={当前RSI:.1f}< {下限:.0f}, 低位信号通过"}
        return {"通过": False, "原因": f"RSI={当前RSI:.1f}< {下限:.0f}, 但信号{哨兵价类型}不匹配低位区间"}

    if 当前RSI > 上限:
        if 哨兵价类型 in 高位信号:
            return {"通过": True, "原因": f"RSI={当前RSI:.1f}> {上限:.0f}, 高位信号通过"}
        return {"通过": False, "原因": f"RSI={当前RSI:.1f}> {上限:.0f}, 但信号{哨兵价类型}不匹配高位区间"}

    return {
        "通过": False,
        "原因": f"RSI={当前RSI:.1f}位于中性区[{下限:.0f},{上限:.0f}], 区间对齐拦截",
    }

