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
- BUG-P1-PERSISTENCE-ATOMICITY

## 当前进行中

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
- TEST-INFRA-P1-014
- TEST-INFRA-P2-OPENPYXL-DEPENDENCY
- TEST-INFRA-P2-ZERO-APPROVAL-FIXTURE
- TEST-P2-017
- DESIGN-P2-018
- COMPAT-P2-019
- TEST-P2-020

### TEST-INFRA-P2-OPENPYXL-DEPENDENCY

状态：BLOCKED-DEFINITION-MISSING（由 TEST-INFRA-P1-014 候选拆分）

证据：默认 `.venv` 收集 `tests/test_public_fundamentals_updater.py` 时缺少 `openpyxl`；`.venv-1` 已安装该依赖且目标测试通过。根 requirements 未声明该依赖，只有 `基本面/requirements-public-data.txt` 声明。

缺失定义：是否要求默认测试环境安装公开数据更新器的可选依赖，还是该测试必须显式跳过/隔离可选依赖；缺少唯一环境契约、允许修改文件和验收条件。

### TEST-INFRA-P2-ZERO-APPROVAL-FIXTURE

状态：BLOCKED-DEFINITION-MISSING（由 TEST-INFRA-P1-014 候选拆分）

证据：真实零审批路径懒创建审批日志；测试夹具强制读取不存在的 `审批对账.jsonl` 并要求非空，导致 `FileNotFoundError`。零审批账户、持仓和审批统计事实保持一致。

缺失定义：零审批场景的测试契约（允许日志不存在还是要求空文件）、允许修改的测试范围和验收条件；当前没有生产缺陷证据。

## 全局规则

- 一个问题一个测试 commit。
- 一个问题一个生产 commit。
- 测试和生产修改不得混合。
- candidate-only failure 必须为零。
- 只有 A 可以关闭问题。
- D/E 不得在稳定主 worktree 写入；启动前报告目标分支/worktree；完成后 A 检查主工作区；遗留未跟踪文件先无损恢复到命名分支再处置；可隔离遗留不得永久阻塞后续事项。
