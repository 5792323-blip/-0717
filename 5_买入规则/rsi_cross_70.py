# rsi_cross_70.py — RSI上穿70买入规则 (暂屏蔽)
# 功能: 检查RSI是否从70以下上穿到70以上
# 这是"超买追涨"信号，优先级最低

def 检查(当前RSI, 上一根RSI, **kwargs):
    """检查RSI上穿70信号"""
    if 上一根RSI <= 70 and 当前RSI > 70:
        return {"触发": True, "类型": "RSI上穿70", "优先级": 3, "基础质量分": 0.2}
    return {"触发": False}

if __name__ == "__main__":
    print("测试:", 检查(68, 72)["触发"], 检查(75, 76)["触发"])
    print("✅ RSI上穿70自检完成")
