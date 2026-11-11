## MODIFIED Requirements

### Requirement: Fixed Execution Log Template
系统 MUST 按固定模板输出执行日志，至少包含开始边界、step1、step2、step3、step4、结束边界；在 step3 中，系统 MUST 为每个待处理规则输出带序号的子步骤定位日志（如 `step3.1`、`step3.2`），并展示账号、区域、安全组可读名称、规则可读名称。

#### Scenario: Full step template emitted
- **WHEN** 系统执行一次完整检查更新流程
- **THEN** 日志中按顺序出现开始边界、step1~step4、结束边界模板信息
- **THEN** step3 对每个目标规则输出 `step3.n：目标安全组：${account} | ${region_id} | ${security_group_name} | ${security_rule_name}`

#### Scenario: Step3 branch logs remain traceable
- **WHEN** 某目标规则在 step3 中被处理
- **THEN** 系统在 step3.n 定位日志后输出“变化并更新”或“未变化并跳过”的结果日志

