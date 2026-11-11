## MODIFIED Requirements

### Requirement: Rule Display Name In Summary Notification

系统 MUST 在汇总通知中展示规则可读名称，并在多云场景下展示云厂商字段以区分阿里云与华为云记录。

#### Scenario: Notification includes provider column

- **GIVEN** 本轮更新结果同时包含阿里云与华为云记录
- **WHEN** 系统生成汇总通知
- **THEN** 表格包含“云厂商”列
- **AND** 每条记录展示对应云厂商名称
