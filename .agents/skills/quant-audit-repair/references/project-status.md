# 项目审计状态

## 稳定开发分支

adaptive-phase1-infrastructure

## 已关闭

- BUG-P2-006
- BUG-P1-005A
- BUG-P1-005B
- 市场流动性观察 UI
- 默认严格预挂单配置契约

## 当前进行中

### BUG-P1-005C

状态：
已关闭。D/E 已完成审批与 execution 显式关联、执行时序兼容及共享账户嵌套/交错回滚修复；Gate 6 统一矩阵通过并已 non-squash 合并。

红测试分支：
test-bug-p1-005c-approval-link

红测试 commit：
5e48f0f7671e29392939de36ded367002b9110e2

红测试 parent：
004e2b1db124ce9005dd65ce6f8a891459f31fad

当前结果：
1 passed, 6 failed

当前阶段：
已完成 Gate 7。

注意：红测试未合并到稳定分支；若稳定分支继续前进，E 开始前由 A 判断是否需要基于最新稳定分支重放或重新验证。

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
