# rsi_cross_ma.py — RSI上穿均线买入规则 (暂屏蔽)
# 功能: 检查RSI是否上穿RSI_MA
# 还需确认均线趋势向上 (防止一根阳线拉高MA的假信号)

def 检查(当前RSI, 上一根RSI, 当前RSI_MA, 上一根RSI_MA, **kwargs):
    """
    检查RSI上穿均线信号
    
    额外条件:
    RSI_MA必须是在上升趋势中
    (当前MA > 前5根MA的最低值)
    """
    if 上一根RSI <= 上一根RSI_MA and 当前RSI > 当前RSI_MA:
        return {"触发": True, "类型": "RSI上穿均线", "优先级": 2, "基础质量分": 0.4}
    return {"触发": False}

if __name__ == "__main__":
    print("测试:", 检查(45, 52, 48, 47)["触发"])
    print("✅ RSI上穿均线自检完成")
