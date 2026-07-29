"""下载和读取按生效日保存的指数历史成分股。"""

import bisect
import csv
import os
from collections import defaultdict
from datetime import datetime


项目目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
默认文件路径 = os.path.join(项目目录, "数据模块", "hs300_历史成分.csv")


def 规范化股票代码(code):
    """把 baostock 的 ``sh.600000`` 统一成项目使用的 ``SH_600000``。"""
    value = str(code or "").strip().upper().replace(".", "_")
    if "_" not in value and len(value) == 6:
        return ("SH_" if value.startswith("6") else "SZ_") + value
    return value


def 读取历史成分股(path=默认文件路径):
    """读取历史快照，返回可按任意日期查询成员资格的对象。"""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"未找到历史成分股文件：{path}")
    snapshots = defaultdict(set)
    with open(path, encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            date = str(row.get("生效日期", ""))[:10]
            stock = 规范化股票代码(row.get("股票代码"))
            if date and stock:
                snapshots[date].add(stock)
    if not snapshots:
        raise ValueError(f"历史成分股文件为空：{path}")
    return 历史成分股池(snapshots)


class 历史成分股池:
    def __init__(self, snapshots):
        self._snapshots = {
            str(date)[:10]: frozenset(规范化股票代码(stock) for stock in stocks)
            for date, stocks in snapshots.items()
        }
        self._dates = sorted(self._snapshots)

    def 成分股(self, date):
        """返回 date 当天生效的最近一期成分；date 早于首期时返回空集。"""
        key = str(date)[:10]
        index = bisect.bisect_right(self._dates, key) - 1
        return self._snapshots[self._dates[index]] if index >= 0 else frozenset()

    def 包含(self, stock, date):
        return 规范化股票代码(stock) in self.成分股(date)

    def 覆盖股票(self, start, end):
        """返回本地行情加载器使用的六位股票代码并集。"""
        result = set()
        for date in self._dates:
            if str(start)[:10] <= date <= str(end)[:10]:
                result.update(self._snapshots[date])
        result.update(self.成分股(start))
        return sorted(stock[-6:] for stock in result)


def 下载沪深300历史成分(start, end, path=默认文件路径):
    """从 Baostock 的周度更新接口查询，并只保存成分实际变更后的快照。"""
    import baostock as bs

    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"Baostock 登录失败：{login.error_msg}")
    try:
        dates_result = bs.query_trade_dates(start_date=str(start), end_date=str(end))
        if dates_result.error_code != "0":
            raise RuntimeError(f"交易日查询失败：{dates_result.error_msg}")
        dates = []
        while dates_result.next():
            row = dict(zip(dates_result.fields, dates_result.get_row_data()))
            if row.get("is_trading_day") == "1":
                dates.append(row["calendar_date"])
        # Baostock 的成分股数据按周一更新。首个交易日保证区间起点也有
        # 可用快照，之后只查询周一，避免对同一版本重复发起数百次请求。
        if dates:
            first_date = dates[0]
            dates = [
                date for date in dates
                if date == first_date or datetime.strptime(date, "%Y-%m-%d").weekday() == 0
            ]

        snapshots = {}
        if os.path.isfile(path):
            with open(path, encoding="utf-8-sig", newline="") as source:
                for row in csv.DictReader(source):
                    effective_date = str(row.get("生效日期", ""))[:10]
                    stock = 规范化股票代码(row.get("股票代码"))
                    if effective_date and stock:
                        snapshots.setdefault(effective_date, {})[stock] = row.get("股票名称", "")
        for date in dates:
            result = bs.query_hs300_stocks(date=date)
            if result.error_code != "0":
                # Baostock 的匿名会话会在连续查询后过期；重登后重试当前
                # 日期，保证分段下载不会因会话边界留下缺口。
                bs.logout()
                login = bs.login()
                result = bs.query_hs300_stocks(date=date)
            if result.error_code != "0":
                raise RuntimeError(f"{date} 成分股查询失败：{result.error_msg}")
            rows = []
            while result.next():
                rows.append(dict(zip(result.fields, result.get_row_data())))
            if not rows:
                raise RuntimeError(f"{date} 未返回沪深300成分股")
            effective_date = str(rows[0]["updateDate"])[:10]
            snapshots[effective_date] = {
                规范化股票代码(row["code"]): row.get("code_name", "")
                for row in rows
            }
    finally:
        bs.logout()

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=["生效日期", "股票代码", "股票名称"])
        writer.writeheader()
        for effective_date in sorted(snapshots):
            for stock, name in sorted(snapshots[effective_date].items()):
                writer.writerow({"生效日期": effective_date, "股票代码": stock, "股票名称": name})
    return {"快照数": len(snapshots), "文件路径": path, "更新时间": datetime.now().isoformat(timespec="seconds")}
