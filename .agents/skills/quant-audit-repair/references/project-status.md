# 项目审计状态

## 稳定开发分支

adaptive-phase1-infrastructure

## 已关闭

- BUG-P2-006
- BUG-P1-005A
- BUG-P1-005B
- BUG-P1-005C
- CONFIG-P2-BOOL-NORMALIZATION
- 市场流动性观察 UI
- 默认严格预挂单配置契约

## 当前进行中

### BUG-P1-011

状态：BLOCKED-DEFINITION-MISSING

证据：截至稳定 HEAD `5a20c555cb019aec23c95645ed009e0c586bca0f`，该编号仅出现在本状态文件；Git commit、分支、tag、测试、代码、审计报告和日志均无直接定义。

已搜索范围：全量 Git message/diff、分支/tag/merge、tests 文件名与注释、AGENTS/SKILL/status、策略文档与审计报告、BUG-P1-005A/B/C 上下文、未跟踪审计摘要及远端可见引用。

排除候选：ARCH-001/002/003、CLI 实验身份、审批生命周期、部分成交、页面指标、乱序库存、缺失数据等均无唯一映射证据。

缺失人工信息：原始问题描述、唯一业务契约、expected/actual、确定性复现步骤、最小允许文件范围和验收条件。

阻塞日期：2026-08-02。

## 其他未关闭事项

- BUG-P1-011
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
