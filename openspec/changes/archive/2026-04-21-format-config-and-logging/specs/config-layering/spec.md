## ADDED Requirements

### Requirement: Three-part Configuration Model
系统 MUST 将运行配置拆分为基础配置、阿里云配置、通知配置三部分，并允许分别加载。

#### Scenario: Load three config files successfully
- **WHEN** 用户提供基础配置（JSON）、阿里云配置（YAML）、通知配置（JSON）
- **THEN** 系统成功启动并生成可用运行配置对象

### Requirement: Aliyun YAML Hierarchy Support
系统 MUST 支持阿里云 YAML 的多层结构：`accounts[] -> security_groups[] -> rules[]`，并支持多账号、多安全组、多规则。

#### Scenario: Parse multiple accounts and rules
- **WHEN** YAML 中包含多个 `accounts`，且每个账号下包含多个安全组与规则
- **THEN** 系统成功解析为完整目标列表并用于后续更新流程

### Requirement: Rule Readable Identifier In Configuration
系统 MUST 在阿里云配置中支持规则可读标识字段（`name` 或 `alias`）并在内部统一为可展示名称。

#### Scenario: Use alias as display name
- **WHEN** 规则配置同时包含规则 ID 与 `alias`
- **THEN** 系统在内部目标对象中保留该可读名称用于日志与通知展示

