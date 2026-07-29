#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成多股票回放总入口，选择股票后在同一页面查看对应报告。"""

import html
import os
import re
import sys
from pathlib import Path


项目根目录 = Path(__file__).resolve().parent.parent
实验目录 = 项目根目录 / "10_实验记录"
输出目录 = 项目根目录 / "9_输出"
输出路径 = 项目根目录 / "9_输出" / "多股票K线回放.html"
sys.path.insert(0, str(项目根目录))
from 数据模块.股票名称 import 股票显示名称


def _股票代码(path: Path):
    match = re.search(r"K线回放_(\d{6})(?:_|$)", path.stem)
    if not match:
        match = re.search(r"(?:^|_)(\d{6})(?:$|_)", path.stem)
    return match.group(1) if match else None


def _找到报告():
    """每只股票选择最近生成的单股票报告，避免把数百份历史报告同时载入。"""
    reports = {}
    # 只读取固定命名的当前报告，历史实验页面不再进入入口列表。
    for path in 输出目录.glob("K线回放_*.html"):
        if not re.fullmatch(r"K线回放_\d{6}\.html", path.name):
            continue
        code = _股票代码(path)
        if code and code != "回放":
            reports[code] = path
    return reports


def 生成():
    reports = _找到报告()
    输出路径.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for code, report in sorted(reports.items()):
        relative = os.path.relpath(report, 输出路径.parent).replace(os.sep, "/")
        rows.append(
            f'<button class="stock-item" data-code="{code}" data-src="{html.escape(relative)}">'
            f'<span>{股票显示名称(code)}</span><small>点击查看 K 线与成交</small></button>'
        )
    stock_html = "".join(rows) or '<div class="empty">暂未找到单股票回放报告，请先运行回测。</div>'
    first_src = html.escape(os.path.relpath(next(iter(reports.values()), Path("")), 输出路径.parent).replace(os.sep, "/")) if reports else ""
    page = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>多股票 K 线回放工作台</title>
<style>
*{{box-sizing:border-box}}html,body{{height:100%;margin:0;background:#0b0e14;color:#d1d4dc;font-family:-apple-system,"Microsoft YaHei",sans-serif;overflow:hidden}}
.app{{height:100%;display:grid;grid-template-rows:52px 1fr}}
.top{{display:flex;align-items:center;gap:16px;padding:0 18px;background:#131722;border-bottom:1px solid #2a2e39}}
.top h1{{font-size:16px;color:#e94560;margin:0}}.top span{{font-size:12px;color:#787b86}}
.body{{display:grid;grid-template-columns:270px minmax(0,1fr);min-height:0;gap:6px;padding:6px}}
.sidebar{{display:flex;flex-direction:column;min-height:0;background:#131722;border-radius:6px;border:1px solid #2a2e39}}
.side-head{{padding:10px;border-bottom:1px solid #2a2e39}}.side-head strong{{font-size:13px}}.side-head input{{width:100%;margin-top:8px;padding:7px 8px;border:1px solid #2a2e39;border-radius:4px;background:#0b0e14;color:#fff}}
.stock-list{{overflow:auto;padding:5px}}.stock-item{{width:100%;display:flex;justify-content:space-between;align-items:center;padding:8px 9px;margin-bottom:3px;border:1px solid transparent;border-radius:4px;background:transparent;color:#d1d4dc;text-align:left;cursor:pointer}}
.stock-item:hover,.stock-item.active{{background:#1e222d;border-color:#5b67ea}}.stock-item span{{font-weight:700}}.stock-item small{{color:#787b86;font-size:10px}}
.viewer{{min-width:0;min-height:0;background:#1e222d;border-radius:6px;overflow:hidden;position:relative}}.viewer iframe{{display:block;width:100%;height:100%;border:0;background:#0b0e14}}.empty{{padding:20px;color:#787b86;font-size:12px}}
@media(max-width:900px){{.body{{grid-template-columns:210px minmax(0,1fr)}}}}
</style></head><body><div class="app"><header class="top"><h1>多股票 K 线回放工作台</h1><span id="selected">请选择股票</span><span>左侧选择股票，右侧查看完整回放</span></header><main class="body"><aside class="sidebar"><div class="side-head"><strong>回测股票</strong><input id="search" placeholder="搜索股票代码"></div><div class="stock-list" id="stockList">{stock_html}</div></aside><section class="viewer"><iframe id="viewer" title="股票回放" src="{first_src}"></iframe></section></main></div>
<script>
const items=[...document.querySelectorAll('.stock-item')], viewer=document.getElementById('viewer'), selected=document.getElementById('selected');
function choose(item){{items.forEach(x=>x.classList.remove('active'));item.classList.add('active');viewer.src=item.dataset.src;selected.textContent=item.querySelector('span').textContent+' · K线与成交回放';}}
items.forEach(item=>item.addEventListener('click',()=>choose(item)));
if(items[0]) choose(items[0]);
document.getElementById('search').addEventListener('input',e=>{{const q=e.target.value.trim();items.forEach(x=>x.style.display=!q||x.dataset.code.includes(q)?'flex':'none')}});
</script></body></html>'''
    输出路径.write_text(page, encoding="utf-8")
    print(f"多股票回放页面: {输出路径}")
    print(f"股票数量: {len(reports)}")
    return 输出路径


if __name__ == "__main__":
    生成()
