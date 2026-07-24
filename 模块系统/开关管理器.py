#!/usr/bin/env python3
"""统一模块开关；中央配置存在时优先于旧YAML的分散开关。"""

import os

import yaml


class 模块配置错误(RuntimeError):
    pass


class 模块开关管理器:
    允许状态 = {"完成", "实验", "未就绪"}

    def __init__(self, 配置目录, 文件名="模块开关配置.yaml"):
        self.配置目录 = os.path.abspath(配置目录)
        self.路径 = os.path.join(self.配置目录, 文件名)
        self.配置 = {}
        self.类别 = {}
        self.启用中央开关 = os.path.exists(self.路径)
        if self.启用中央开关:
            with open(self.路径, encoding="utf-8") as source:
                self.配置 = yaml.safe_load(source) or {}
            self.类别 = self.配置.get("模块类别", {}) or {}
            self.验证()

    def 验证(self):
        errors = []
        for category, modules in self.类别.items():
            if not isinstance(modules, dict):
                errors.append(f"{category}必须是字典")
                continue
            for module_id, item in modules.items():
                if not isinstance(item, dict):
                    errors.append(f"{category}.{module_id}必须是字典")
                    continue
                status = item.get("状态", "完成")
                if status not in self.允许状态:
                    errors.append(f"{category}.{module_id}未知状态:{status}")
                if item.get("启用", False) and status == "未就绪":
                    errors.append(f"{category}.{module_id}未就绪，不允许启用")
        if errors:
            raise 模块配置错误("; ".join(errors))
        return True

    def 获取(self, category, module_id):
        return self.类别.get(category, {}).get(module_id)

    def 是否启用(self, category, module_id, legacy_default=False):
        if not self.启用中央开关:
            return bool(legacy_default)
        item = self.获取(category, module_id)
        if item is None:
            return bool(legacy_default)
        if item.get("启用", False) and item.get("状态") == "未就绪":
            raise 模块配置错误(f"{category}.{module_id}未就绪")
        return bool(item.get("启用", False))

    def 扁平清单(self):
        records = []
        for category, modules in self.类别.items():
            for module_id, item in modules.items():
                records.append({"类别": category, "标识": module_id, **item})
        return records

    def 统计(self):
        records = self.扁平清单()
        return {
            "总模块数": len(records),
            "已启用": sum(bool(item.get("启用")) for item in records),
            "完成": sum(item.get("状态") == "完成" for item in records),
            "实验": sum(item.get("状态") == "实验" for item in records),
            "未就绪": sum(item.get("状态") == "未就绪" for item in records),
        }
