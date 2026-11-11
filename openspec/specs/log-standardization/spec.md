## ADDED Requirements

### Requirement: Fixed Execution Log Template
系统 MUST 按固定模板输出执行日志，至少包含开始边界、step1、step2、step3、step4、结束边界。

#### Scenario: Full step template emitted
- **WHEN** 系统执行一次完整检查更新流程
- **THEN** 日志中按顺序出现开始边界、step1~step4、结束边界模板信息

### Requirement: Daily Log File Naming
系统 MUST 按天写入日志文件，文件名格式 MUST 为 `ip_sync_YYYYMMDD.log`。

#### Scenario: Log file name follows daily pattern
- **WHEN** 程序在任意日期启动并写日志
- **THEN** 日志文件名符合 `ip_sync_YYYYMMDD.log` 命名规范

### Requirement: Log Retention Cleanup
系统 MUST 默认保留最近 7 天日志，并自动清理超期文件。

#### Scenario: Expired logs are removed
- **WHEN** 日志目录中存在超过 7 天的历史日志文件
- **THEN** 系统在清理周期中删除超期日志并保留最近 7 天日志

### Requirement: Sensitive Information Redaction
系统 MUST 避免在日志中输出密钥、密码等敏感信息，且 MUST 避免输出冗长异常堆栈与过细调试信息。

#### Scenario: Secrets are not logged in plaintext
- **WHEN** 运行配置包含访问密钥或 SMTP 密码
- **THEN** 日志输出不包含上述敏感字段明文

### Requirement: Log Structure Must Remain Stable After Modularization
系统在脚本拆分后 MUST 继续满足既有日志标准化要求，且 MUST 保持开始边界、step1、step2、step3、step4、结束边界等主流程日志语义可识别。

#### Scenario: Modularized implementation preserves log flow structure
- **WHEN** 模块化后的脚本完成一次完整执行
- **THEN** 输出日志仍可识别完整主流程步骤与结束边界
- **THEN** 日志消费者无需因模块拆分而失去对核心执行阶段的定位能力

### Requirement: Target Update Logs Must Preserve Key Fields Across Modules
系统在模块化后 MUST 继续在规则更新相关日志中保留账号、区域、安全组、规则、旧IP、新IP、结果、失败原因等关键字段，且这些字段可以跨模块汇总输出。

#### Scenario: Cross-module logging retains required update fields
- **WHEN** 安全组更新模块处理任一目标规则并生成结果
- **THEN** 日志输出中包含该目标对应的关键定位与结果字段
- **THEN** 即使日志内容由独立日志模块统一输出，也不丢失原有排障所需信息
