import os, csv, glob, json
from datetime import datetime
from collections import defaultdict

初始资金 = 30000000

# 读取MA过滤回测的交易明细
files = glob.glob('10_实验记录/*/交易明细.csv')
ma_filter_files = []
for f in files:
    dirname = os.path.dirname(f)
    ts = os.path.basename(dirname).split('_')[1]
    minute_part = int(ts[:3])
    if 213 <= minute_part <= 214:
        ma_filter_files.append(f)

print(f'找到 {len(ma_filter_files)} 个MA过滤回测文件')

# 读取所有买卖记录
all_trades = []  # [(时间, 类型, 股票代码, 买入价, 仓位金额, 信号类型)]

for csv_path in ma_filter_files:
    dirname = os.path.dirname(csv_path)
    code = os.path.basename(dirname).split('_')[-1]
    
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['类型'] == '买入':
                买入价 = float(row['买入价']) if row['买入价'] else 0
                仓位 = float(row['仓位']) if row['仓位'] else 0
                if 买入价 > 0 and 仓位 > 0:
                    all_trades.append((row['时间'], 'buy', code, 买入价, 仓位, row.get('信号类型', '')))
            elif row['类型'] == '卖出':
                卖出价 = float(row['卖出价']) if row['卖出价'] else 0
                盈亏 = float(row['盈亏比例']) if row['盈亏比例'] else 0
                if 卖出价 > 0:
                    all_trades.append((row['时间'], 'sell', code, 卖出价, 0, 盈亏))

print(f'总买卖记录: {len(all_trades)}笔')

# 按时间排序
all_trades.sort(key=lambda x: x[0])

# 模拟组合 - 共享3000万资金池
现金 = 初始资金
持仓 = {}  # {股票代码: {"股数": int, "买入价": float, "占用": float}}

买入记录 = 0
卖出记录 = 0
总买入金额 = 0
总卖出金额 = 0
总费用 = 0

# 权益曲线: 每笔交易后记录
权益点 = [(all_trades[0][0] if all_trades else '开始', 现金, 0, 现金)]

for 时间, 类型, 代码, 价格, 额外, 信号 in all_trades:
    if 类型 == 'buy':
        买入价 = 价格
        仓位金额 = 额外
        
        # 计算股数 (从仓位金额和买入价反推)
        股数 = int(仓位金额 / 买入价 / 100) * 100
        if 股数 < 100:
            continue
        
        实际金额 = 股数 * 买入价
        费用 = max(实际金额 * 0.00035, 5)  # 佣金万2.5+过户费万0.1,最低5元
        
        if 现金 >= 实际金额 + 费用:
            现金 -= 实际金额 + 费用
            持仓[代码] = {"股数": 股数, "买入价": 买入价, "占用": 实际金额}
            买入记录 += 1
            总买入金额 += 实际金额
            总费用 += 费用
    
    elif 类型 == 'sell':
        卖出价 = 价格
        盈亏比例 = 额外
        
        if 代码 in 持仓:
            股数 = 持仓[代码]["股数"]
            买入价成本 = 持仓[代码]["买入价"]
            实际金额 = 股数 * 卖出价
            费用 = max(实际金额 * 0.00035, 5)  # 佣金
            印花税 = 实际金额 * 0.0005  # 卖出印花税万5
            总收入 = 实际金额 - 费用 - 印花税
            
            盈亏 = 总收入 - 持仓[代码]["占用"]
            
            现金 += 总收入
            卖出记录 += 1
            总卖出金额 += 总收入
            总费用 += 费用 + 印花税
            
            del 持仓[代码]
    
    # 记录权益
    持仓市值 = sum(p["股数"] * p["买入价"] for p in 持仓.values())
    总权益 = 现金 + 持仓市值
    权益点.append((时间, 现金, 持仓市值, 总权益))

# 最终状态
持仓市值 = sum(p["股数"] * p["买入价"] for p in 持仓.values())
总权益 = 现金 + 持仓市值
权益点.append(('最终', 现金, 持仓市值, 总权益))

# 统计
总利润 = 总权益 - 初始资金
总收益率 = 总利润 / 初始资金 * 100

# 计算最大回撤
最高 = 初始资金
最大回撤 = 0
回撤开始 = ''

for 时间, _, _, 权益 in 权益点:
    if 权益 > 最高:
        最高 = 权益
    回撤 = (最高 - 权益) / 最高 * 100 if 最高 > 0 else 0
    if 回撤 > 最大回撤:
        最大回撤 = 回撤
        回撤开始 = 时间

# 计算胜率（按交易对）
# 从交易记录配对买卖
盈利对 = 0
亏损对 = 0
卖出的交易 = [t for t in all_trades if t[1] == 'sell']
for t in 卖出的交易:
    盈亏 = t[4]  # 盈亏比例
    if isinstance(盈亏, (int, float)):
        if 盈亏 > 0:
            盈利对 += 1
        else:
            亏损对 += 1

总交易对 = 盈利对 + 亏损对

print()
print('='*60)
print('  组合回测结果 (MA过滤 + 3000万共享资金)')
print('='*60)
print(f'  初始资金:        {初始资金:>12,}元')
print(f'  最终权益:        {总权益:>12,.0f}元')
print(f'  总利润:          {总利润:>+12,.0f}元')
print(f'  总收益率:        {总收益率:>+12.2f}%')
print(f'  最大回撤:        {最大回撤:>12.2f}%')
print(f'  总交易对:        {总交易对:>12}笔')
print(f'  盈利:            {盈利对:>12}笔')
print(f'  亏损:            {亏损对:>12}笔')
print(f'  胜率:            {盈利对/总交易对*100:>12.1f}%')
print(f'  买入总金额:      {总买入金额:>12,.0f}元')
print(f'  卖出总收入:      {总卖出金额:>12,.0f}元')
print(f'  总费用(含税):    {总费用:>12,.0f}元')
print(f'  最终持仓数:      {len(持仓):>12}只')

# 保存结果
ts = datetime.now().strftime('%Y%m%d_%H%M%S')
结果 = {
    '时间': ts,
    '初始资金': 初始资金,
    '最终权益': round(总权益),
    '总利润': round(总利润),
    '总收益率': round(总收益率, 2),
    '最大回撤': round(最大回撤, 2),
    '总交易对': 总交易对,
    '胜率': round(盈利对/总交易对*100, 1) if 总交易对 > 0 else 0,
    '买入总金额': round(总买入金额),
    '卖出总收入': round(总卖出金额),
    '总费用': round(总费用),
    '最终持仓': len(持仓),
}

with open(f'10_实验记录/组合回测_{ts}.json', 'w', encoding='utf-8') as f:
    json.dump(结果, f, ensure_ascii=False, indent=2)

# 保存权益曲线（精简版，每10个点取一个）
with open(f'10_实验记录/组合权益曲线_{ts}.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['时间', '现金', '持仓市值', '总权益', '回撤%'])
    for i, (时间, 现金v, 持仓v, 权益v) in enumerate(权益点):
        if i % 10 == 0 or i == len(权益点) - 1:
            回撤 = (最高 - 权益v) / 最高 * 100
            writer.writerow([时间, round(现金v,2), round(持仓v,2), round(权益v,2), round(回撤,2)])

print(f'\n结果已保存')
print('='*60)
