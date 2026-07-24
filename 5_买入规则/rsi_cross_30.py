# rsi_cross_30.py — RSI上穿30买入规则 (暂屏蔽)
# 功能: 检查RSI是否从30以下上穿到30以上
# 这是"超卖反弹"信号，优先级第二

def 检查(当前RSI, 上一根RSI, **kwargs):
    """检查RSI上穿30信号"""
    if 上一根RSI <= 30 and 当前RSI > 30:
        return {"触发": True, "类型": "RSI上穿30", "优先级": 1, "基础质量分": 0.7}
    return {"触发": False}

if __name__ == "__main__":
    print("测试:", 检查(28, 32)["触发"], 检查(35, 36)["触发"])
    print("✅ RSI上穿30自检完成")
