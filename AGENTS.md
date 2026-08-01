## 多 Agent 审计修复流程

当用户要求代码审计、逻辑检查、bug 修复、回测验证或提到 A/B/C/D/E 时：

1. 使用项目 Skill `$quant-audit-repair`。
2. 主线程承担 A Controller。
3. 使用项目 custom agents：`b_architect`、`c_contract_auditor`、`d_test_engineer`、`e_fixer`。
4. 只读审查可以并行。
5. D 和 E 的写入必须串行。
6. 无红测试不得修改生产代码。
7. 未经用户明确允许不得 push、merge 或删除 stash。
