# 运行程序

| 程序 | 功能 |
|---|---|
| `interactive_backtest_app.py` | 启动参数回测网页；单股和多股拥有独立参数与模块开关。 |
| `run_backtest.py` | 统一单股/多股批量回测入口，输出机器可读结果。 |
| `auto_runner.py` | 自动执行亏损诊断后再调用参数优化。 |

推荐启动页面：

```bash
python3 -m 运行程序.interactive_backtest_app --host 127.0.0.1 --port 8501 --no-open
```

如果启动时提示 `Operation not permitted`，通常是运行环境禁止监听本地端口（例如受限沙盒/托管环境）。请在你自己的系统终端里运行，或更换到允许监听端口的环境。
