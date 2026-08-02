# 项目审计状态

## 稳定开发分支

adaptive-phase1-infrastructure

## 已关闭

- BUG-P2-006
- BUG-P1-005A
- BUG-P1-005B
- BUG-P1-005C
- CONFIG-P2-BOOL-NORMALIZATION
- CONFIG-P2-BOOL-NORMALIZATION
- 市场流动性观察 UI
- 默认严格预挂单配置契约

## 当前进行中

### BUG-P1-PERSISTENCE-ATOMICITY

状态：已关闭。正式三 YAML 保存已具备临时 staging、备份替换、失败回滚和残留清理；Gate 6 通过并已合并。

Expected：一次逻辑保存全部成功或保持保存前状态；失败后逐字节回滚、清理临时文件并明确返回错误。

Actual：多文件写入缺少统一原子提交/跨文件回滚证据；需 B/C 先确认入口事务边界。

失败注入点：任一 YAML/JSON 临时文件替换或写入失败。

允许测试范围：仅新增该问题编号的保存失败注入测试；不得修改 CONFIG-P2 测试。

初步生产范围：保存调用链涉及的最小持久化模块，待 Gate 2 冻结。

验收条件：parent 稳定复现；candidate 全部文件逐字节恢复、错误明确、无临时残留，candidate-only failure 为 0。

### BUG-P1-011

状态：BLOCKED-DEFINITION-MISSING

证据：截至稳定 HEAD `5a20c555cb019aec23c95645ed009e0c586bca0f`，该编号仅出现在本状态文件；Git commit、分支、tag、测试、代码、审计报告和日志均无直接定义。

已搜索范围：全量 Git message/diff、分支/tag/merge、tests 文件名与注释、AGENTS/SKILL/status、策略文档与审计报告、BUG-P1-005A/B/C 上下文、未跟踪审计摘要及远端可见引用。

排除候选：ARCH-001/002/003、CLI 实验身份、审批生命周期、部分成交、页面指标、乱序库存、缺失数据等均无唯一映射证据。

缺失人工信息：原始问题描述、唯一业务契约、expected/actual、确定性复现步骤、最小允许文件范围和验收条件。

阻塞日期：2026-08-02。

### TEST-INFRA-P1-014

状态：BLOCKED-DEFINITION-MISSING

证据：HEAD `79e3c9738be1b8cdf78927ce8f760c3fb9426a2d` 下无该编号的原始定义。只读调查发现两个互不等价候选：默认 `.venv` 缺少 `openpyxl` 导致测试收集失败；另一个共享账户零审批测试夹具强制要求不存在的审批日志文件。B/C/D 对编号含义无法统一，不能任选其一建立红测试。

缺失人工信息：应修复的唯一基础设施契约、expected/actual、允许文件范围和验收条件。

阻塞日期：2026-08-02。

## 其他未关闭事项

- BUG-P1-011
- BUG-P1-PERSISTENCE-ATOMICITY
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
- D/E 不得在稳定主 worktree 写入；启动前报告目标分支/worktree；完成后 A 检查主工作区；遗留未跟踪文件先无损恢复到命名分支再处置；可隔离遗留不得永久阻塞后续事项。
