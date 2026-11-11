# Design: IP 变更 SMTP 邮件通知

## 1. Goals
- 在不改变现有主流程语义的前提下，为“多目标更新结果”新增 SMTP 汇总邮件通知。
- 保持通知能力可配置、可关闭、可观测，并满足最小安全要求。
- 与现有失败告警机制协同，避免重复告警与敏感信息泄露。

## 2. Non-goals
- 本期不新增 webhook/IM 新通知渠道。
- 本期不做复杂模板系统与国际化。
- 本期不引入外部队列或异步消息系统。

## 3. High-level Flow
```text
run_cycle
  ├─ 解析公网 IP + 一致性判定
  ├─ 遍历账号/目标并执行更新
  │    ├─ changed=false -> skip
  │    └─ changed=true -> 记录 TargetUpdateResult(success/failed)
  ├─ 结束遍历后构建 NotificationBatch(汇总结果)
  ├─ NotificationDispatcher.dispatch(batch)
  │    └─ SMTPEmailChannel.send(batch)
  │          ├─ success -> log notify.sent
  │          └─ failed  -> log notify.failed + 触发现有失败告警
  └─ 持久化状态并返回退出码
```

## 4. Components
1. **TargetUpdateResult（逐条结果）**
   - 每条目标记录都保存可通知字段：
     - `occurred_at`
     - `account`
     - `region`
     - `security_group_id`
     - `rule_identifier`
     - `previous_ip`
     - `current_ip`
     - `reason`（固定 `public_ip_changed`）
     - `result`（`success` / `failed`）
     - `error_summary`（仅失败时，脱敏）
   - 严禁携带密钥、原始异常栈。

2. **NotificationBatch（汇总模型）**
   - 单轮运行结束后生成批次对象：
     - `batch_id`
     - `started_at` / `ended_at`
     - `resolved_ip`
     - `items: List[TargetUpdateResult]`
   - 邮件正文以表格/列表形式逐条展示 `items` 的成功或失败结果。

3. **SMTP Config（配置模型）**
   - 从环境变量读取：
     - `NOTIFY_ENABLED`
     - `NOTIFY_SMTP_HOST`
     - `NOTIFY_SMTP_PORT`
     - `NOTIFY_SMTP_USERNAME`
     - `NOTIFY_SMTP_PASSWORD`
     - `NOTIFY_SMTP_USE_TLS`
     - `NOTIFY_EMAIL_FROM`
     - `NOTIFY_EMAIL_TO`（逗号分隔）
     - `NOTIFY_RATE_LIMIT_SECONDS`（可选，默认复用告警限频策略）

4. **SMTPEmailChannel（发送器）**
   - 负责 SMTP 连接、邮件主题与正文拼装、发送与错误封装。
   - 仅接受 `NotificationBatch`，确保邮件包含逐条更新结果。

5. **NotificationDispatcher（分发器）**
   - 根据开关决定是否发送。
   - 负责汇总级限频 key 生成（建议 `notify:batch:{date}:{account_scope}`）。
   - 发送失败时打结构化日志，并调用现有失败告警能力（不额外扩大失败面）。

6. **Observability（可观测）**
   - 新增结构化事件：
     - `notify.skipped`（未启用/限频/无收件人）
     - `notify.sent`（发送成功）
     - `notify.failed`（发送失败）
     - `notify.retry`（单次重试记录，包含 attempt）
   - 日志字段仅包含必要元数据与错误摘要。

7. **Retry Policy（重试策略）**
   - SMTP 发送失败后执行重试，最大重试次数为 3 次。
   - 建议配置项：`NOTIFY_RETRY_COUNT`，默认值固定为 `3`。
   - 退避策略可采用固定间隔或指数退避，但需在实现中保持可预测。

## 5. Integration Points
- 在 [`run_cycle()`](src/ip_sync.py:504) 的目标遍历逻辑中累计每条 `TargetUpdateResult`（成功/失败）。
- 在单轮遍历结束后统一触发一次汇总通知发送（而非逐条即时发送）。
- 当本轮存在安全组更新尝试时，增加日志阶段 `step4`，输出汇总通知发送结果（成功/失败、尝试次数、最终状态）。
- 复用现有状态存储机制，必要时扩展一个轻量通知限频状态文件（可与 [`load_alert_state()`](src/ip_sync.py:398) / [`save_alert_state()`](src/ip_sync.py:410) 复用结构）。
- 失败协同复用 [`send_webhook_alert()`](src/ip_sync.py:415) 作为“通知发送失败”的告警出口。

## 6. Error Handling Strategy
- 配置不完整：
  - 若 `NOTIFY_ENABLED=true` 但 SMTP 关键参数缺失，记录 `notify.skipped` + 配置错误摘要，不中断主流程。
- 无可通知记录：
  - 当本轮 `items` 为空（无变更且无失败）时，按配置可跳过发送并记录 `notify.skipped`。
- 发送失败：
  - 记录 `notify.failed`，并在每次重试时记录 `notify.retry`。
  - 达到最大重试次数仍失败时触发现有告警。
  - 不影响本轮 IP 更新主结果退出码（通知属于附加能力）。
- 限频命中：
  - 记录 `notify.skipped`（reason=`rate_limited`）。

## 7. Security Considerations
- SMTP 凭证仅允许环境变量注入，不写入文件与日志。
- 邮件正文与日志字段采用白名单映射，禁止透传原始异常堆栈与凭证。
- 发件地址与收件人列表进行基础格式校验，避免明显误配。

## 8. Testing Strategy
- 单元测试：
  - 通知开关关闭时不发送。
  - 变更成功路径触发发送（mock SMTP）。
  - SMTP 异常路径验证最大重试 3 次，并在最终失败后触发告警函数。
  - 限频逻辑生效。
  - 发生安全组配置修改时，日志包含 `step4` 且记录通知结果。
- 回归测试：
  - 不影响既有 `run_cycle` 成功/失败退出码语义。

## 9. Documentation Plan
- 在使用文档新增“SMTP 通知配置”章节：
  - 最小配置示例
  - 常见错误（认证失败、端口/TLS 不匹配）
  - 安全建议（凭证注入、日志检查）

## 10. Open Questions
- 汇总范围固定策略：全局单封（所有账号）还是按账号分封。
- 限频状态是否与告警状态文件共用（实现简单）或隔离（语义清晰）。
