from 因子模块.顶部风险 import 顶部风险
from 因子模块.压缩完成度 import 压缩完成度
from 因子模块.状态反转 import 状态反转
from 因子模块.稳定吸引度 import 稳定吸引度
from 因子模块.因子管理器 import 因子管理器


def _bar(close, volume=1000, atr=1):
    return {
        "前复权_收盘": close,
        "成交量": volume,
        "ATR_14": atr,
    }


def test_买入过滤只使用上一根已完成状态():
    factor = 顶部风险({"买入过滤阈值": 0})
    factor.每根K线处理(_bar(100), {})
    # 首根没有已完成状态，不能因为当前K线的数据拦截本根哨兵成交。
    assert factor.买入前检查(_bar(100), {})["允许买入"] is True
    factor.每根K线处理(_bar(102), {})
    # 第二根开始使用上一根状态；阈值为0时验证过滤已生效。
    assert factor.买入前检查(_bar(102), {})["允许买入"] is False


def test_卖出过滤不会创建订单():
    factor = 顶部风险({"卖出放行阈值": 0})
    factor.每根K线处理(_bar(100), {})
    factor.每根K线处理(_bar(102), {})
    result = factor.卖出信号过滤({}, _bar(102), {}, {"英文标识": "atr_trailing"})
    assert result["允许卖出"] is True
    assert not hasattr(factor, "卖出前检查") or factor.卖出前检查({}, _bar(102), {})["触发卖出"] is False


def test_买入指标相互独立且使用上一根状态():
    factors = [
        压缩完成度({"买入过滤阈值": 0, "买入高值拦截": False}),
        状态反转({"买入过滤阈值": 0, "买入高值拦截": False}),
        稳定吸引度({"买入过滤阈值": 0, "买入高值拦截": False}),
    ]
    for factor in factors:
        factor.每根K线处理(_bar(100), {})
        assert factor.买入前检查(_bar(100), {})["允许买入"] is True
        factor.每根K线处理(_bar(102), {})
        assert factor.指标键 in factor.当前状态


def test_买入过滤不会改变已有持仓的网格路径():
    factor = 压缩完成度({"买入过滤阈值": 1.0, "买入高值拦截": False})
    factor.每根K线处理(_bar(100), {})
    factor.每根K线处理(_bar(102), {})
    result = factor.买入前检查(_bar(102), {"当前持仓": {"600519": {"股数": 100}}})
    assert result["允许买入"] is True
    assert "网格加仓" in result["说明"]


def test_因子管理器不会误把导入的基类当作插件(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "因子配置.yaml").write_text(
        "全局因子开关: true\n因子列表:\n  顶部风险:\n    启用: true\n    参数: {}\n",
        encoding="utf-8",
    )
    (config / "模块开关配置.yaml").write_text(
        "模块类别:\n  扩展因子:\n    顶部风险:\n      启用: true\n      状态: 实验\n",
        encoding="utf-8",
    )
    manager = 因子管理器(str(config))
    assert type(manager.已启用因子["顶部风险"]).__name__ == "顶部风险"
