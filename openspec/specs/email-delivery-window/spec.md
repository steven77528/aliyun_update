## ADDED Requirements

### Requirement: Night Window Delayed Delivery
系统 MUST 在 22:00（含）到次日 07:00（不含）之间，将通知记录进入待发送队列而不是立即发送邮件。

#### Scenario: Delay notification during night window
- **WHEN** 某条 IP 变更记录发生时间在 22:00 到次日 07:00 之间
- **THEN** 系统不立即发送邮件，并将该记录纳入待发送集合

### Requirement: Unified Dispatch At 07:00
系统 MUST 在每日 07:00 对夜间待发送集合执行统一发送，并在邮件中保留每条记录的实际修改时间。

#### Scenario: Send buffered notifications at 07:00
- **WHEN** 到达每日 07:00 且存在夜间待发送记录
- **THEN** 系统发送汇总邮件，且邮件中的修改时间字段展示记录的实际修改时间

#### Scenario: Aggregate all night modifications in one email
- **WHEN** 22:00-07:00 之间发生多次修改
- **THEN** 次日 07:00 的统一发送邮件中包含该窗口内所有修改记录

### Requirement: Two-hour Delivery Throttling
系统 MUST 保持每 2 小时最多发送一次邮件的策略不变，并将 07:00 统一发送纳入同一限频口径。

#### Scenario: Enforce throttling after 07:00 dispatch
- **WHEN** 系统在 07:00 已完成统一发送且 2 小时内再次触发发送条件
- **THEN** 系统不重复发送邮件，直到 2 小时窗口满足

