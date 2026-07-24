"""买入订单的数据时序边界。

严格预挂单只允许使用上一根已完成 K 线生成的哨兵价。
本根预挂模式也只使用上一根状态，但允许本根最高价触发成交。
"""

STRICT_PRECOMPUTED = "precomputed_stop_entry"
SAME_BAR_ENTRY = "same_bar_entry"
CLOSE_NEXT_OPEN = "close_confirm_next_open"
LEGACY_SAME_BAR = SAME_BAR_ENTRY
TB_REPLAY = "tb_replay"

ALIASES = {
    "intrabar_breakout": SAME_BAR_ENTRY,
    "legacy_same_bar_lookahead": SAME_BAR_ENTRY,
    SAME_BAR_ENTRY: SAME_BAR_ENTRY,
    TB_REPLAY: TB_REPLAY,
    STRICT_PRECOMPUTED: STRICT_PRECOMPUTED,
    CLOSE_NEXT_OPEN: CLOSE_NEXT_OPEN,
}


def 规范化模式(模式):
    value = str(模式 or STRICT_PRECOMPUTED)
    if value not in ALIASES:
        raise ValueError(f"不支持的买入时机模式: {value}")
    return ALIASES[value]


def 哨兵价可执行(模式, 已确认, 当根收盘发生上穿=False):
    """判断已在上一根形成的哨兵价是否可执行。"""
    mode = 规范化模式(模式)
    if mode == TB_REPLAY:
        return bool(已确认 or 当根收盘发生上穿)
    # 严格预挂模式的价格本身就是上根收盘后生成的条件单；
    # 不得再读当根收盘 RSI 来倒推盘中成交。
    return True


def 使用收盘确认(模式):
    return 规范化模式(模式) == CLOSE_NEXT_OPEN


def 是严格模式(模式):
    return 规范化模式(模式) != TB_REPLAY


def 允许旧版本根回填(模式):
    """只有明确选择旧版对照模式才允许收盘后回填本根成交。"""
    return 规范化模式(模式) == TB_REPLAY
