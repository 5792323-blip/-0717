"""Alpha + RSI/哨兵独立实验门控。

该模块只生成实验诊断，不调用执行器、不修改账户，也不改变正式策略。
"""


def 评估入场(alpha_record, stock, rsi_signal, sentinel_result):
    """判断一笔候选是否同时满足 Alpha、RSI 和哨兵条件。"""
    record = alpha_record or {}
    candidates = set(record.get("候选股票") or [])
    stock = str(stock)
    alpha_ok = stock in candidates
    rsi_ok = bool(rsi_signal)
    sentinel_ok = bool((sentinel_result or {}).get("满足"))
    passed = alpha_ok and rsi_ok and sentinel_ok
    reasons = []
    if not alpha_ok:
        reasons.append("不在Alpha候选")
    if not rsi_ok:
        reasons.append("RSI信号未通过")
    if not sentinel_ok:
        reasons.append("哨兵条件未通过")
    return {
        "通过": passed,
        "股票代码": stock,
        "Alpha通过": alpha_ok,
        "RSI通过": rsi_ok,
        "哨兵通过": sentinel_ok,
        "原因": "三项条件均通过" if passed else "；".join(reasons),
    }


def 生成对照标签(alpha_enabled):
    """返回实验组标签，明确 Alpha 仍处于旁路实验。"""
    return "Alpha+RSI哨兵实验" if alpha_enabled else "RSI哨兵基线"
