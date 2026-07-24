# rsi_position_filter.py — RSI位置过滤因子
# 功能: RSI太高时不买，避免追涨

def 检查(哨兵价类型, K线数据, 状态, 配置):
    """
    检查当前RSI是否在合理范围内
    
    传入:
        哨兵价类型 - 哨兵价形成类型
        K线数据   - 当前K线数据
        状态      - 公共状态
        配置      - YAML配置
    
    传出:
        {"通过": True/False, "原因": "..."}
    """
    当前RSI = K线数据.get('RSI_14', 50)
    最高RSI = 配置.get('最高RSI', 70)
    
    if 当前RSI > 最高RSI:
        return {"通过": False, "原因": f"RSI={当前RSI:.1f}>{最高RSI}, 拦截"}
    
    return {"通过": True, "原因": f"RSI={当前RSI:.1f}, 通过"}
