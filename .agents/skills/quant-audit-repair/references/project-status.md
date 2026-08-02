# 项目审计状态

## 稳定开发分支

adaptive-phase1-infrastructure

## 已关闭

- BUG-P2-006
- BUG-P1-005A
- BUG-P1-005B
- BUG-P1-005C
- 市场流动性观察 UI
- 默认严格预挂单配置契约

## 当前进行中

## 其他未关闭事项

- BUG-P1-011
- CONFIG-P2-BOOL-NORMALIZATION
- TEST-INFRA-P1-014
- TEST-P2-017
- DESIGN-P2-018
- COMPAT-P2-019
- TEST-P2-020

## 全局规则

- 一个问题一个测试 commit。
- 一个问题一个生产 commit。
- 测试和生产修改不得混合。
- candidate-only failure 必须为零。
- 只有 A 可以关闭问题。
