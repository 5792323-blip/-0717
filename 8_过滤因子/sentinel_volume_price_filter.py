#!/usr/bin/env python3
"""哨兵形成后的量价确认因子。

本因子只读取哨兵形成时锁定的量价快照，不参与反推价、哨兵价或订单计算。
默认只记录结论；只有配置为“正式拦截”时才会阻止原有买入流程。
"""

import math


def _数值(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _范围值(value, fallback):
    value = _数值(value)
    return fallback if value is None else value


def 检查(哨兵价类型, K线数据, 状态, 配置):
    适用信号 = 配置.get("适用信号", []) or []
    if 适用信号 and 哨兵价类型 not in 适用信号:
        return {"通过": True, "原因": f"{哨兵价类型}不在量价因子适用范围", "适用": False}

    快照 = 状态.get("哨兵量价快照") or {}
    if not 快照.get("有效", False):
        放行 = bool(配置.get("历史不足时放行", True))
        return {
            "通过": 放行,
            "原因": "哨兵形成前量价历史不足，" + ("放行" if 放行 else "拦截"),
            "适用": True,
            "快照": 快照,
        }

    结果 = []
    启用项 = 配置.get("启用项", {}) or {}
    模式 = str(配置.get("运行模式", "只记录"))

    def 添加(name, passed, reason):
        if bool(启用项.get(name, False)):
            结果.append({"名称": name, "通过": bool(passed), "原因": reason})

    相对量能 = _数值(快照.get("相对量能"))
    缩量比例 = _数值(快照.get("缩量比例"))
    价格变化 = _数值(快照.get("近期价格变化"))
    趋势涨幅 = _数值(快照.get("趋势涨幅"))
    收盘强度 = _数值(快照.get("收盘强度"))
    上影比例 = _数值(快照.get("上影比例"))
    单根跌幅 = _数值(快照.get("单根跌幅"))

    添加("缩量回撤衰竭", (
        价格变化 is not None and 价格变化 < 0
        and 缩量比例 is not None
        and 缩量比例 <= _范围值(配置.get("缩量比例上限"), 0.85)
    ), f"价格变化={价格变化!s}，缩量比例={缩量比例!s}，上限={配置.get('缩量比例上限', 0.85)}")
    添加("量价转强确认", (
        价格变化 is not None and 价格变化 >= _范围值(配置.get("近期价格涨幅下限"), 0.0)
        and 相对量能 is not None
        and 相对量能 >= _范围值(配置.get("相对量能下限"), 1.10)
    ), f"近期涨幅={价格变化!s}，相对量能={相对量能!s}，量能下限={配置.get('相对量能下限', 1.10)}")
    添加("放量趋势确认", (
        趋势涨幅 is not None and 趋势涨幅 >= _范围值(配置.get("趋势涨幅下限"), 0.0)
        and 相对量能 is not None
        and 相对量能 >= _范围值(配置.get("相对量能下限"), 1.10)
    ), f"趋势涨幅={趋势涨幅!s}，相对量能={相对量能!s}，量能下限={配置.get('相对量能下限', 1.10)}")
    添加("收盘承接强度", (
        收盘强度 is not None
        and 收盘强度 >= _范围值(配置.get("最低收盘强度"), 0.60)
    ), f"收盘强度={收盘强度!s}，下限={配置.get('最低收盘强度', 0.60)}")
    添加("上影抛压过滤", (
        上影比例 is not None
        and 上影比例 <= _范围值(配置.get("最大上影比例"), 0.35)
    ), f"上影比例={上影比例!s}，上限={配置.get('最大上影比例', 0.35)}")
    添加("异常放量下跌过滤", not (
        单根跌幅 is not None and 单根跌幅 <= _范围值(配置.get("异常跌幅阈值"), -0.02)
        and 相对量能 is not None
        and 相对量能 >= _范围值(配置.get("异常量能阈值"), 1.50)
        and 收盘强度 is not None
        and 收盘强度 <= _范围值(配置.get("异常收盘强度上限"), 0.35)
    ), f"单根跌幅={单根跌幅!s}，相对量能={相对量能!s}，收盘强度={收盘强度!s}")

    未通过 = [item for item in 结果 if not item["通过"]]
    通过 = not 未通过
    if not 结果:
        通过 = True
        原因 = "没有启用量价子因子，放行"
    else:
        原因 = "全部量价子因子通过" if 通过 else "未通过：" + "、".join(item["名称"] for item in 未通过)
    return {
        "通过": 通过 if 模式 == "正式拦截" else True,
        "原始通过": 通过,
        "原因": 原因 + ("（只记录）" if 模式 != "正式拦截" else ""),
        "适用": True,
        "运行模式": 模式,
        "量价子因子": 结果,
        "快照": 快照,
    }
