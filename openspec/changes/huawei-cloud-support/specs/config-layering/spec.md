## MODIFIED Requirements

### Requirement: Three-part Configuration Model

系统 MUST 支持基础配置、云厂商配置、通知配置三段式配置模型；其中云厂商配置推荐使用统一 `cloud.yaml` 文件。

#### Scenario: Load unified cloud config successfully

- **GIVEN** 用户提供 `cloud.yaml`
- **AND** 文件顶层包含 `aliyun` 与 `huawei` 任一或两者
- **WHEN** 系统加载应用配置
- **THEN** 系统成功解析所有已配置云厂商账号与目标规则

### Requirement: Aliyun YAML Hierarchy Support

系统 MUST 继续兼容现有阿里云层级结构，并在统一 `cloud.yaml` 中支持将阿里云配置放在 `aliyun` 顶层字段下。

#### Scenario: Parse legacy aliyun-only config

- **GIVEN** 用户仍提供旧格式阿里云配置，根节点为 `accounts`
- **WHEN** 系统加载云厂商配置
- **THEN** 系统按阿里云旧格式完成解析

### Requirement: Multi-provider Hierarchy Support

系统 MUST 支持在统一云配置文件中分别声明阿里云与华为云账号、安全组、规则层级结构。

#### Scenario: Parse huawei accounts and rules

- **GIVEN** `cloud.yaml` 顶层存在 `huawei`
- **AND** 其中包含账号、区域、安全组、规则层级
- **WHEN** 系统加载云厂商配置
- **THEN** 系统生成带云厂商标识的华为云目标规则列表
