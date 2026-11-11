## ADDED Requirements

### Requirement: Script Responsibilities Must Be Split Into Dedicated Modules
系统 MUST 将现有脚本中的配置管理、IP 地址管理、安全组规则更新、邮件通知、日志管理职责拆分为独立模块文件，并由统一编排入口负责按既定顺序调用各模块。

#### Scenario: Main workflow delegates to dedicated modules
- **WHEN** 系统执行一次完整的公网 IP 检查与安全组更新流程
- **THEN** 配置读取、IP 获取与比较、规则更新、通知生成发送、日志输出分别由独立模块承担
- **THEN** 主入口仅负责流程编排与结果汇总，不直接承载上述具体职责实现

### Requirement: Module Interactions Must Use Explicit Interfaces
系统 MUST 通过明确的函数调用在模块之间传递输入与输出，且 MUST 避免依赖隐式全局状态，以保证模块具备高内聚、低耦合特性。

#### Scenario: Module dependencies are explicit
- **WHEN** 任一模块需要使用配置、运行上下文或上游处理结果
- **THEN** 调用方通过显式参数传入所需数据
- **THEN** 被调用模块不依赖未声明的全局共享状态完成核心逻辑

### Requirement: Refactoring Must Preserve Existing Operational Semantics
系统在完成模块化拆分后 MUST 保持现有配置语义、IP 变化判断逻辑、安全组更新触发条件、通知触发时机与日志主流程结构不变，除非另有明确变更说明。

#### Scenario: Refactored flow remains behaviorally equivalent
- **WHEN** 使用相同配置与相同输入条件分别运行拆分前后脚本
- **THEN** 两者对“是否需要更新规则”的判断结果一致
- **THEN** 两者产生的更新结果、通知触发结论与日志主步骤语义保持一致
