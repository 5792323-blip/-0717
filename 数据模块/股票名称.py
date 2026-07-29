"""股票代码与名称的本地映射。

名称只是展示和审计字段，无法从本地历史成分表查到时保留代码并明确标记。
"""

import csv
import os
import re


项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_名称映射 = None


def 规范化股票代码(value):
    code = str(value or "").strip().upper()
    code = re.sub(r"^(SH_|SZ_|BJ_)", "", code)
    match = re.search(r"(\d{6})", code)
    return match.group(1) if match else code


def _加载名称映射():
    global _名称映射
    if _名称映射 is not None:
        return _名称映射
    mapping = {}
    path = os.path.join(项目根目录, "数据模块", "hs300_历史成分.csv")
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                code = 规范化股票代码(row.get("股票代码"))
                name = str(row.get("股票名称") or "").strip()
                if code and name:
                    mapping[code] = name
    except (OSError, csv.Error):
        pass
    _名称映射 = mapping
    return mapping


def 获取股票名称(value):
    return _加载名称映射().get(规范化股票代码(value), "名称待补充")


def 股票显示名称(value):
    code = 规范化股票代码(value)
    return f"{code} · {获取股票名称(code)}"
