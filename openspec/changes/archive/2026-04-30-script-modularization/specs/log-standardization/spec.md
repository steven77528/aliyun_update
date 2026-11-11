## ADDED Requirements

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
