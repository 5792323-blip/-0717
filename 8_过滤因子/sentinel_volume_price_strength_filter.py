from .sentinel_volume_price_common import 检查哨兵量价条件


def 检查(哨兵价类型, K线数据, 状态, 配置):
    return 检查哨兵量价条件(哨兵价类型, 状态, 配置, "price_strength")
