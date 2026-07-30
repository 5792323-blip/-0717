"""JSONL追加式审计日志。"""

import json
import os
from datetime import datetime


日志文件名 = {
    "运行清单": "运行清单.json",
    "决策快照": "决策快照.jsonl",
    "订单意图": "订单意图.jsonl",
    "可执行订单": "可执行订单.jsonl",
    "成交结果": "成交结果.jsonl",
    "预算审批": "预算审批.jsonl",
    "审批对账": "审批对账.jsonl",
    "事件时钟对账": "事件时钟对账.jsonl",
    "市场评分": "市场评分.jsonl",
    "Alpha排序": "Alpha排序.jsonl",
    "账户变化": "账户变化.jsonl",
    "守恒检查": "守恒检查.jsonl",
    "错误记录": "错误记录.jsonl",
}


class 事件日志:
    def __init__(self, 根目录, run_id, account_id, code_version="", config_hash=""):
        self.目录 = os.path.join(os.path.abspath(根目录), str(run_id))
        self.run_id = str(run_id)
        self.account_id = str(account_id)
        self.code_version = str(code_version)
        self.config_hash = str(config_hash)
        self._序号 = 0
        os.makedirs(self.目录, exist_ok=True)
        self._写入_json(
            日志文件名["运行清单"],
            {"run_id": self.run_id, "account_id": self.account_id,
             "created_at": datetime.now().isoformat(),
             "code_version": self.code_version, "config_hash": self.config_hash},
            覆盖=True,
        )

    def _写入_json(self, 文件名, payload, 覆盖=False):
        path = os.path.join(self.目录, 文件名)
        mode = "w" if 覆盖 else "a"
        with open(path, mode, encoding="utf-8") as target:
            json.dump(payload, target, ensure_ascii=False, default=str, separators=(",", ":"))
            if not 覆盖:
                target.write("\n")
            target.flush()
            os.fsync(target.fileno())

    def 记录(self, 事件类型, payload, trade_date="", symbol=""):
        self._序号 += 1
        row = {
            "run_id": self.run_id, "account_id": self.account_id,
            "event_id": payload.get("event_id", ""),
            "event_sequence": self._序号, "event_type": 事件类型,
            "trade_date": str(trade_date), "symbol": str(symbol),
            "created_at": datetime.now().isoformat(),
            "code_version": self.code_version, "config_hash": self.config_hash,
            "payload": payload,
        }
        self._写入_json(日志文件名.get(事件类型, "事件.jsonl"), row)
        return row

    def 记录错误(self, error, event_type=""):
        return self.记录("错误记录", {"event_id": "", "错误类型": type(error).__name__,
                                  "错误信息": str(error), "关联事件类型": event_type})
