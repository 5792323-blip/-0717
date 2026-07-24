#!/usr/bin/env python3
"""每个模块的统一独立小程序：列表、审计、查看和单次调用。"""

import argparse
import importlib
import inspect
import json
import os
import sys


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 项目根目录)

from 模块系统 import 模块开关管理器
from 因子模块.因子基类 import 因子基类


def 导入模块(item):
    path = item.get("模块")
    return importlib.import_module(path) if path else None


def 审计单个(category, module_id, item):
    result = {
        "类别": category, "标识": module_id, "名称": item.get("名称", module_id),
        "启用": bool(item.get("启用")), "状态": item.get("状态"), "导入成功": True,
        "接口完整": True, "问题": [],
    }
    if category == "核心模块":
        result["可启用"] = result["状态"] != "未就绪"
        return result
    try:
        module = 导入模块(item)
    except Exception as error:
        result["导入成功"] = False
        result["接口完整"] = False
        result["问题"].append(str(error))
        result["可启用"] = False
        return result
    if category in ("买入规则", "过滤因子", "卖出规则") and not callable(getattr(module, "检查", None)):
        result["接口完整"] = False
        result["问题"].append("缺少检查函数")
    if category == "扩展因子":
        factor_classes = [
            cls for _, cls in inspect.getmembers(module, inspect.isclass)
            if cls is not 因子基类 and issubclass(cls, 因子基类)
        ]
        if not factor_classes:
            result["接口完整"] = False
            result["问题"].append("缺少因子基类子类")
    result["可启用"] = result["状态"] != "未就绪" and result["导入成功"] and result["接口完整"]
    return result


def 审计全部(manager):
    results = [
        审计单个(category, module_id, item)
        for category, modules in manager.类别.items()
        for module_id, item in modules.items()
    ]
    return {
        "统计": manager.统计(),
        "审计通过": all(item["导入成功"] and item["接口完整"] for item in results),
        "可启用数": sum(bool(item["可启用"]) for item in results),
        "模块": results,
    }


def 实例化因子(module, parameters):
    for _, cls in inspect.getmembers(module, inspect.isclass):
        if cls is not 因子基类 and issubclass(cls, 因子基类):
            return cls(parameters)
    raise RuntimeError("没有可实例化的因子类")


def 独立运行(category, item, payload):
    if item.get("状态") == "未就绪":
        raise RuntimeError("模块未就绪，拒绝执行")
    module = 导入模块(item)
    if category == "买入规则":
        return module.检查(**payload)
    if category == "卖出规则":
        return module.检查(**payload)
    if category == "过滤因子":
        return module.检查(
            payload.get("哨兵价类型", ""), payload.get("K线数据", {}),
            payload.get("状态", {}), payload.get("配置", {}),
        )
    if category == "扩展因子":
        factor = 实例化因子(module, payload.get("参数", {}))
        action = payload.get("动作", "买入前检查")
        if action == "每根K线处理":
            return factor.每根K线处理(payload.get("K线数据", {}), payload.get("全局状态", {}))
        if action == "卖出前检查":
            return factor.卖出前检查(payload.get("持仓", {}), payload.get("K线数据", {}), payload.get("全局状态", {}))
        return factor.买入前检查(payload.get("K线数据", {}), payload.get("全局状态", {}))
    raise RuntimeError(f"{category}不支持单次调用")


def main():
    parser = argparse.ArgumentParser(description="策略0717模块独立运行器")
    parser.add_argument("--config", default="1_策略配置")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="列出全部模块")
    subparsers.add_parser("audit", help="导入并审计全部模块")
    show = subparsers.add_parser("show", help="查看单个模块")
    show.add_argument("category")
    show.add_argument("module_id")
    run = subparsers.add_parser("run", help="独立运行单个模块")
    run.add_argument("category")
    run.add_argument("module_id")
    run.add_argument("--input", default="{}", help="JSON输入")
    args = parser.parse_args()

    manager = 模块开关管理器(args.config)
    if args.command == "list":
        output = {"统计": manager.统计(), "模块": manager.扁平清单()}
    elif args.command == "audit":
        output = 审计全部(manager)
    else:
        item = manager.获取(args.category, args.module_id)
        if item is None:
            raise SystemExit(f"未找到模块: {args.category}.{args.module_id}")
        output = {"类别": args.category, "标识": args.module_id, **item}
        if args.command == "run":
            output["运行结果"] = 独立运行(args.category, item, json.loads(args.input))
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
