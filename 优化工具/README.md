# 优化工具

`auto_optimize.py` 使用 Optuna 做多股票参数优化，并严格区分训练期和验证期。通常由 `运行程序/auto_runner.py` 调用；需要单独运行时使用：

```bash
python3 -m 优化工具.auto_optimize --help
```
