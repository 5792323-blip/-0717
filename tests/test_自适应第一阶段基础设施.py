import json

from 自适应基础设施.事件记录.事件日志 import 事件日志
from 自适应基础设施.事件记录.基线指纹 import 结果指纹
from 自适应基础设施.标识管理.事件编号 import 生成编号
from 自适应基础设施.守恒检查.检查器 import (
    检查资金守恒,
    检查持仓守恒,
    检查非负状态,
)
from 自适应基础设施.数据结构.接口 import 成交结果, 转为字典
from 自适应基础设施.旧系统适配.旧执行器适配器 import 旧执行器适配器
from 自适应基础设施.组合审批.审批适配器 import 影子对账
from 自适应基础设施.事件记录.事件时钟 import 比较事件顺序
from 自适应基础设施.市场评分.市场评分 import 市场评分器
from 自适应基础设施.市场评分.诊断 import 诊断状态
from 自适应基础设施.市场评分.归因 import 状态归因
from 自适应基础设施.市场评分.评估报告 import 生成评估报告
from 自适应基础设施.市场评分.Active归因 import 生成Active归因


class _假记录器:
    def __init__(self):
        self.交易列表 = []


class _假执行器:
    股票代码 = "600519"

    def __init__(self):
        self.当前现金 = 10000.0
        self.当前持仓 = {}
        self.交易记录器 = _假记录器()

    def 每根K线处理(self, _, __):
        self.当前现金 -= 1005.0
        self.当前持仓["600519"] = {"股数": 100}
        self.交易记录器.交易列表.append({
            "类型": "买入", "成交数量": 100, "买入价": 10.0,
            "仓位": 1000.0, "总成本": 1005.0, "交易费用": 5.0,
            "时间": "2026-01-01",
        })


def test_编号在相同输入下稳定且不依赖随机状态():
    assert 生成编号("order", "run-1", "600519", 3) == 生成编号(
        "order", "run-1", "600519", 3
    )
    assert 生成编号("order", "run-1", "600519", 3) != 生成编号(
        "order", "600519", "run-1", 3
    )


def test_成交现金方向与守恒():
    buy = 成交结果(
        "e1", "o1", "i1", "600519", "BUY", "FILLED", 100, 100,
        10.0, 1000.0, 5.0, 0.0, 0.0, -1005.0, "2026-01-01"
    )
    sell = 成交结果(
        "e2", "o2", "i2", "600519", "SELL", "FILLED", 100, 100,
        11.0, 1100.0, 5.0, 0.55, 0.0, 1094.45, "2026-01-02"
    )
    assert buy.net_cash_change < 0
    assert sell.net_cash_change > 0
    assert 检查资金守恒(5000, 3995, buy.net_cash_change)["通过"]
    assert 检查持仓守恒(0, 100, 100, 0)["通过"]
    assert 检查持仓守恒(100, 0, 0, 100)["通过"]
    assert 检查非负状态(0, 0)["通过"]


def test_jsonl日志追加且包含运行上下文(tmp_path):
    logger = 事件日志(str(tmp_path), "run-1", "BASELINE_ACTIVE")
    payload = {"event_id": "e1", "值": 1}
    logger.记录("账户变化", payload, "2026-01-01", "600519")
    logger.记录("账户变化", {"event_id": "e2", "值": 2}, "2026-01-01", "600519")
    path = tmp_path / "run-1" / "账户变化.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["event_sequence"] for row in rows] == [1, 2]
    assert all(row["run_id"] == "run-1" for row in rows)
    assert all(row["account_id"] == "BASELINE_ACTIVE" for row in rows)


def test_标准数据结构可以序列化():
    result = 成交结果(
        "e1", "o1", "i1", "600519", "BUY", "FILLED", 100, 100,
        10.0, 1000.0, 5.0, 0.0, 0.0, -1005.0, "2026-01-01"
    )
    assert 转为字典(result)["account_applied"] is False


def test_旧执行器适配器只读取结果不重复扣款(tmp_path):
    logger = 事件日志(str(tmp_path), "run-1", "BASELINE_ACTIVE")
    executor = _假执行器()
    adapter = 旧执行器适配器("run-1", "BASELINE_ACTIVE", "test", logger)
    result = adapter.处理(executor, {"日期": "2026-01-01"}, 0, "600519")
    assert executor.当前现金 == 8995.0
    assert executor.当前持仓["600519"]["股数"] == 100
    assert len(result["成交结果"]) == 1
    assert result["守恒检查"]["资金守恒"]["通过"]
    assert result["守恒检查"]["持仓守恒"]["通过"]


def test_基线指纹包含三类对账结果():
    import pandas as pd
    trades = pd.DataFrame([{"时间": "2026-01-01", "类型": "买入", "成交数量": 100,
                            "买入价": 10.0, "交易费用": 5.0}])
    curve = pd.DataFrame([{"日期": "2026-01-01", "现金": 8995.0,
                           "持仓市值": 1000.0, "权益": 9995.0, "持仓数量": 100}])
    result = 结果指纹(trades, curve, 9995.0)
    assert set(result) == {"trade_hash", "daily_account_hash", "final_equity_hash"}
    assert all(len(value) == 64 for value in result.values())


def test_旧审批映射与Shadow对账不改变审批事实():
    approval, reconciliation = 影子对账({
        "股票代码": "600519", "时间": "2026-01-01", "结果": "实际成交",
        "请求股数": 100, "成交股数": 100, "成交价": 10.0, "原因": "账户批准",
    }, "run-1", "BASELINE_ACTIVE", 1)
    assert approval.status == "APPROVED"
    assert approval.requested_budget == 1000.0
    assert approval.approved_budget == 1000.0
    assert reconciliation.explained is True
    assert reconciliation.difference_type is None


def test_多股共享账户Shadow审批映射保持正式结果(tmp_path):
    import contextlib
    import io
    import os
    from 组合回测.统一多股执行器 import 运行共享账户回测

    config_dir = os.path.abspath("1_策略配置")
    options = {
        "stocks": ["600519", "000001", "300059"],
        "start": "2020-01-01",
        "end": "2020-12-31",
        "capital": 2000000,
        "config_dir": config_dir,
        "allow_partial_fill": True,
    }
    with contextlib.redirect_stdout(io.StringIO()):
        baseline = 运行共享账户回测(**options)
        shadow = 运行共享账户回测(
            **options,
            audit_run_id="test-phase2-multi",
            audit_log_root=str(tmp_path),
            approval_shadow=True,
        )
    assert baseline["live"]["实际成交"] == shadow["live"]["实际成交"]
    assert baseline["live"]["当前权益"] == shadow["live"]["当前权益"]
    assert baseline["组合权益曲线"] == shadow["组合权益曲线"]
    rows = [
        json.loads(line)
        for line in (tmp_path / "test-phase2-multi" / "审批对账.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert rows
    assert all(row["payload"]["explained"] for row in rows)
    assert shadow["live"]["审批模式"] == "Shadow"
    assert shadow["live"]["Shadow审批数"] == len(rows)
    assert shadow["live"]["Shadow未解释差异"] == 0


def test_静态Active在未完成事件拆分前安全拒绝():
    import contextlib
    import io
    import os
    import pytest
    from 组合回测.统一多股执行器 import 运行共享账户回测

    with pytest.raises(RuntimeError, match="尚未接入事件拆分"):
        with contextlib.redirect_stdout(io.StringIO()):
            运行共享账户回测(
                ["600519"], "2020-01-01", "2020-12-31", 2000000,
                os.path.abspath("1_策略配置"), 审批模式="静态Active",
            )


def test_目标事件时钟只比较顺序不修改记录():
    records = [{"类型": "买入"}, {"类型": "卖出"}, {"类型": "买入"}]
    result = 比较事件顺序(records)
    assert result["实际事件顺序"] == ["买入", "卖出", "买入"]
    assert result["目标事件顺序"] == ["卖出", "买入", "买入"]
    assert result["是否需要调整"] is True
    assert records == [{"类型": "买入"}, {"类型": "卖出"}, {"类型": "买入"}]
    assert result["是否混合买卖"] is True
    assert result["买入数量"] == 2
    assert result["卖出数量"] == 1


def test_市场评分状态诊断统计切换和持续时间():
    result = 诊断状态([
        {"状态": "ATTACK", "市场评分": 0.8},
        {"状态": "ATTACK", "市场评分": 0.7},
        {"状态": "DEFENSE", "市场评分": 0.4},
    ])
    assert result["记录数"] == 3
    assert result["状态切换次数"] == 1
    assert result["状态分布"] == {"ATTACK": 2, "DEFENSE": 1}
    assert result["最短状态持续点数"] == 1


def test_市场评分只使用生效日前数据(tmp_path):
    import pandas as pd
    index = pd.DataFrame({
        "date": pd.date_range("2020-01-01", periods=130),
        "close": [100.0 + i for i in range(130)],
    })
    path = tmp_path / "index.pkl"
    index.to_pickle(path)
    stock = pd.DataFrame({
        "日期": index["date"].dt.strftime("%Y-%m-%d"),
        "不复权_收盘": index["close"],
    })
    result = 市场评分器(str(path), [stock]).计算("2020-05-10")
    assert result["生效日期"] == "2020-05-10"
    assert result["指数日期"] < result["生效日期"]
    assert set(result["有效组件"]) == {"趋势", "广度", "稳定度"}


def test_市场状态连续确认和危机恢复迟滞():
    from 自适应基础设施.市场评分.市场评分 import 市场评分器
    scorer = 市场评分器("不存在的指数文件")
    scorer._确认状态 = "NORMAL"
    assert [scorer._更新确认状态("ATTACK") for _ in range(2)] == ["NORMAL", "NORMAL"]
    assert scorer._更新确认状态("ATTACK") == "ATTACK"
    scorer._确认状态 = "CRISIS"
    assert [scorer._更新确认状态("NORMAL") for _ in range(4)] == ["CRISIS"] * 4
    assert scorer._更新确认状态("NORMAL") == "NORMAL"


def test_市场状态收益回撤归因():
    result = 状态归因(
        [{"状态": "ATTACK"}, {"状态": "ATTACK"}, {"状态": "DEFENSE"}],
        [{"权益": 100.0}, {"权益": 110.0}, {"权益": 105.0}],
    )
    assert abs(result["ATTACK"]["区间收益率"] - 0.1) < 1e-9
    assert result["DEFENSE"]["最大回撤"] == 0.0


def test_市场评分Active前评估报告():
    report = 生成评估报告(
        [{"状态": "ATTACK", "市场评分": 0.8}, {"状态": "ATTACK", "市场评分": 0.7},
         {"状态": "ATTACK", "市场评分": 0.6}],
        [{"权益": 100.0}, {"权益": 101.0}, {"权益": 102.0}],
    )
    assert report["结论"] == "建议进入只限制新增仓位的Active实验"


def test_市场评分Active必须保留Shadow日志():
    import contextlib
    import io
    import os
    import pytest
    from 组合回测.统一多股执行器 import 运行共享账户回测
    with pytest.raises(ValueError, match="必须同时启用Shadow"):
        with contextlib.redirect_stdout(io.StringIO()):
            运行共享账户回测(
                ["600519"], "2020-01-01", "2020-12-31", 2000000,
                os.path.abspath("1_策略配置"), 市场评分Active=True,
            )


def test_市场评分只禁止无持仓股票开仓():
    from 策略引擎.规则执行器 import 规则执行器
    executor = object.__new__(规则执行器)
    executor.运行参数 = {"市场评分禁止新开仓": True}
    executor.当前持仓 = {"600519": {"股数": 100}}
    assert "600519" in executor.当前持仓
    assert "000001" not in executor.当前持仓


def test_状态诊断忽略历史不足记录():
    result = 诊断状态([
        {"状态": "历史不足"}, {"状态": "ATTACK", "市场评分": 0.8},
        {"状态": "ATTACK", "市场评分": 0.7},
    ])
    assert result["有效状态数"] == 2
    assert result["状态切换次数"] == 0


def test_Active实验归因报告():
    base = {"live": {"实际成交": 10, "实际买入": 5, "实际卖出": 5, "当前权益": 100.0, "最大回撤": 0.2}, "组合权益曲线": [1]}
    shadow = {"live": {"实际成交": 10, "当前权益": 100.0, "Shadow未解释差异": 0}, "组合权益曲线": [1]}
    active = {"live": {"实际成交": 8, "实际买入": 4, "实际卖出": 4, "当前权益": 105.0, "最大回撤": 0.1}, "组合权益曲线": [1]}
    result = 生成Active归因(base, shadow, active)
    assert result["基线与Shadow结果一致"] is True
    assert result["Active相对基线"]["成交变化"] == -2
    assert result["Active相对基线"]["最终权益变化"] == 5.0
