## ADDED Requirements

### Requirement: Rule Display Name In Update Logs
系统 MUST 在 step3 规则更新日志中展示规则可读名称（`name/alias`），用于定位具体规则。

#### Scenario: Step3 log contains readable rule name
- **WHEN** 系统执行某条规则的源 CIDR 更新
- **THEN** step3 日志包含该规则可读名称与更新结果

### Requirement: Rule Display Name In Summary Notification
系统 MUST 在邮件汇总通知中展示每条规则的可读名称（`name/alias`），并保留每条结果的成功/失败信息。

#### Scenario: Notification includes readable rule names
- **WHEN** 系统发送更新结果汇总邮件
- **THEN** 邮件正文中每条记录均包含规则可读名称及对应更新状态

