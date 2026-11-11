## MODIFIED Requirements

### Requirement: Fixed Execution Log Template

系统 MUST 按固定模板输出执行日志；在多云场景下，step3 相关日志 MUST 能区分目标规则所属云厂商。

#### Scenario: Step3 log indicates cloud provider

- **GIVEN** 本轮处理中包含多个云厂商目标规则
- **WHEN** 系统输出 step3 目标定位日志或更新结果日志
- **THEN** 日志可通过账号、区域、安全组、规则及云厂商字段定位具体目标
