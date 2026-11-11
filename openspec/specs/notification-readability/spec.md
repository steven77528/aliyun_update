## ADDED Requirements

### Requirement: Rule Display Name In Update Logs
系统 MUST 在 step3 规则更新日志中展示规则可读名称（`name/alias`），用于定位具体规则。

#### Scenario: Step3 log contains readable rule name
- **WHEN** 系统执行某条规则的源 CIDR 更新
- **THEN** step3 日志包含该规则可读名称与更新结果

### Requirement: Rule Display Name In Summary Notification
系统 MUST 在邮件汇总通知中展示每条规则的可读名称（`name/alias`），并保留每条结果的成功/失败信息；邮件内容 MUST 采用结构化格式，包含固定主题、强调首行、生成时间、当前公网 IP、统计信息与失败详情表格。

#### Scenario: Notification includes readable rule names and structured body
- **WHEN** 系统发送更新结果汇总邮件
- **THEN** 邮件主题为 `[阿里云安全组自动更新] ---- 更新通知`
- **THEN** 邮件正文包含“公网IP变更，安全组规则变更汇总通知”强调行，并采用 1.5 倍行距
- **THEN** 邮件正文第二行显示“生成时间：YYYY-MM-DD HH:mm:ss”，且时间为邮件实际发送时间
- **THEN** 邮件正文包含当前公网 IP、记录总数/成功/失败统计
- **THEN** 邮件正文中每条记录均包含规则可读名称及对应更新状态

#### Scenario: Failure detail table is shown for failed records
- **WHEN** 汇总结果中存在失败记录
- **THEN** 邮件 MUST 以表格展示失败详情，表头包含序号、修改时间、账号、区域、安全组、规则、旧IP、新IP、结果、失败原因
- **THEN** 表格各列数据居中展示，且“安全组”“规则”单元格分别按“名称/ID”双行展示
- **THEN** 失败原因列在成功记录时显示 `-`，失败记录时显示具体失败原因

#### Scenario: Modification time in table uses actual record time
- **WHEN** 邮件渲染失败详情表格
- **THEN** “修改时间”列使用记录实际修改时间，格式为 `YYYY-MM-DD HH:mm:ss`

### Requirement: Notification Content Must Remain Readable After Modularization
系统在脚本拆分后 MUST 继续满足既有通知可读性要求，邮件主题、正文结构、统计信息与失败明细展示 MUST 不因模块边界调整而被削弱或遗漏。

#### Scenario: Modularized implementation preserves notification readability
- **WHEN** 模块化后的脚本发送一次更新结果汇总邮件
- **THEN** 邮件仍包含既定主题、强调首行、生成时间、当前公网 IP、统计信息与失败详情结构
- **THEN** 接收方无需适配新的非兼容通知格式

### Requirement: Notification Triggering Must Preserve Existing Semantics
系统在模块化后 MUST 保持与原有流程一致的通知触发时机与结果汇总语义，避免因通知模块独立而导致重复发送、漏发或状态错配。

#### Scenario: Notification dispatch remains consistent after refactor
- **WHEN** 一次运行流程产生成功、失败或跳过结果
- **THEN** 通知模块基于统一汇总结果按既有规则发送或不发送通知
- **THEN** 邮件中每条记录的状态与主流程最终结果保持一致
