import time, os, sys, json
项目根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 项目根目录)
import warnings
warnings.filterwarnings('ignore')

from 回测引擎.backtest_engine import 跑回测, 保存结果

# Read HS300 stock list
with open('数据模块/hs300_list.txt', 'r') as f:
    lines = [l.strip() for l in f if l.strip()]
stock_codes = [l.split('_')[1] if '_' in l else l for l in lines]

start_time_str = time.strftime("%Y-%m-%d %H:%M")
print(f'HS300全量回测 开始')
print(f'总股票数: {len(stock_codes)}只')
print(f'初始资金: 30,000,000元')
print(f'买入逻辑: 1万元开仓 / 100股起步')
print(f'开始时间: {start_time_str}')
print(f'{"="*50}')

results = []
start_time = time.time()
errors = 0

for i, code in enumerate(stock_codes):
    t0 = time.time()
    try:
        结果 = 跑回测(code, 初始资金=30000000)
        if 结果:
            saved = 保存结果(结果)
            results.append({
                'code': code,
                'trades': 结果.get('买入次数', 0),
                'win_rate': 结果.get('胜率', 0),
                'avg_return': 结果.get('平均盈亏', 0),
                'total_return': 结果.get('总收益率', 0),
                'final_cash': 结果.get('最终现金', 0),
                'profit': 结果.get('最终现金', 30000000) - 30000000,
            })
            elapsed = time.time() - t0
            pct = round((i+1)/len(stock_codes)*100)
            print(f'  [{i+1}/{len(stock_codes)}] {code} 交易:{结果["买入次数"]}笔 收益:{结果["总收益率"]:+.2f}% ({elapsed:.1f}s) {pct}%')
    except Exception as e:
        errors += 1
        print(f'  ERROR [{i+1}/{len(stock_codes)}] {code} 失败: {e}')
    
    if (i+1) % 50 == 0:
        ts = time.strftime("%H%M%S")
        interim_path = f'10_实验记录/_全量中间结果_{ts}.json'
        with open(interim_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f'  中间结果已保存 ({i+1}只)')

total_time = time.time() - start_time
minutes = int(total_time // 60)
seconds = int(total_time % 60)

print()
print('='*50)
print('HS300全量回测 完成')
print('='*50)
print(f'总股票数: {len(stock_codes)}只')
print(f'成功: {len(results)}只')
print(f'失败: {errors}只')
print(f'总耗时: {minutes}分{seconds}秒')

if results:
    有交易 = [r for r in results if r['trades'] > 0]
    盈利 = [r for r in results if r['profit'] > 0]
    亏损 = [r for r in results if r['profit'] <= 0]
    total_profit = sum(r['profit'] for r in results)
    total_capital = 30000000
    
    print()
    print('  全量统计')
    print(f'  有交易的股票: {len(有交易)}/{len(results)}只')
    print(f'  盈利股票: {len(盈利)}只')
    print(f'  亏损股票: {len(亏损)}只')
    print(f'  胜率(股票级): {len(盈利)/max(len(有交易),1)*100:.1f}%')
    print(f'  总利润: {total_profit:+,.0f}元')
    print(f'  总收益率: {total_profit/total_capital*100:+.2f}%')
    print(f'  平均每只利润: {total_profit/max(len(results),1):+,.0f}元')
    
    有交易.sort(key=lambda r: r['total_return'], reverse=True)
    print()
    print('  TOP10 盈利:')
    for r in 有交易[:10]:
        print(f'    {r["code"]} 交易:{r["trades"]}笔 收益:{r["total_return"]:+8.2f}% 利润:{r["profit"]:+,.0f}')
    
    有交易.sort(key=lambda r: r['total_return'])
    print()
    print('  TOP10 亏损:')
    for r in 有交易[:10]:
        print(f'    {r["code"]} 交易:{r["trades"]}笔 收益:{r["total_return"]:+8.2f}% 利润:{r["profit"]:+,.0f}')
    
    # 统计所有交易的汇总
    总交易数 = sum(r['trades'] for r in 有交易)
    总利润 = total_profit
    print()
    print(f'  所有股票总交易数: {总交易数}笔')
    print(f'  总利润: {总利润:+,.0f}元')
    print(f'  每笔平均利润: {总利润/max(总交易数,1):+,.0f}元')

# Save final results
ts = time.strftime("%Y%m%d_%H%M%S")
final_path = f'10_实验记录/_全量结果_{ts}.json'
with open(final_path, 'w', encoding='utf-8') as f:
    json.dump({
        'total_stocks': len(stock_codes),
        'success': len(results),
        'errors': errors,
        'duration_seconds': total_time,
        'total_profit': total_profit if results else 0,
        'total_return_pct': total_profit/total_capital*100 if results else 0,
        'total_trades': 总交易数 if results else 0,
        'details': results,
    }, f, ensure_ascii=False, indent=2)
print(f'\n详细结果已保存: {final_path}')
