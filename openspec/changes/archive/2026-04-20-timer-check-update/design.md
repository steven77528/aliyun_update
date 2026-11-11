# Design: 定时检查公网 IP 并更新阿里云安全组（扩展版）

## 1. Goals
- 实现最小闭环：定时检查公网 IP → 判断是否变化 → 变化时更新阿里云安全组规则。
- 保证基础可用性：多源 IP 查询、错误可诊断、最小重试能力。
- 支持内置定时循环执行模式（除单次执行外）。
- 支持多账号、多安全组配置与隔离执行。
- 支持失败场景告警（至少 Webhook），并具备限频。

## 2. Non-goals
- 复杂工作流调度平台集成。
- 多告警通道全覆盖（邮件/IM 等）本期不强制。
- 完整 CI/CD 发布流水线。

## 3. High-level Flow
```text
Scheduler(trigger once)
        |
        v
  Fetch IP from multiple sources
        |
        v
  Consensus / fallback decision
        |
        +--> no valid IP -> log error -> end
        |
        v
  Compare with last known IP
        |
   +----+----+
   |         |
 unchanged  changed
   |         |
   v         v
 log skip   call Aliyun SDK update rule
             |
             v
       persist new IP + log result
```

## 4. Components
1. **Scheduler**
   - 支持“单次执行命令 + 内置定时循环执行”。
   - 保留外部 cron 兼容方式。

2. **IP Resolver**
   - 配置多个公网 IP 源（主源 + 备源）。
   - 对结果执行一致性判定：
     - 多数一致则采用。
     - 全不一致则本轮失败并记录告警日志，不更新安全组。

3. **State Store**
   - 记录最近一次成功 IP（例如本地状态文件）。
   - 用于变化判断与幂等更新控制。

4. **Aliyun Security Group Updater**
   - 使用阿里云 SDK 更新目标规则。
   - 支持单账号多安全组/规则更新。
   - 支持多账号配置，账号间隔离执行。
   - 针对限流/瞬时错误做有限重试（指数退避可简化实现）。

5. **Alerting**
   - 失败事件（IP 解析失败、更新失败、连续失败阈值触发）发送 Webhook。
   - 支持告警限频，避免重复告警风暴。

6. **Logging**
   - 每轮执行输出结构化日志：
     - timestamp
     - resolved_ip
     - changed(bool)
     - update_attempted(bool)
     - update_result
     - error_code/error_message(脱敏)

## 5. Configuration (Current Release)
- `CHECK_INTERVAL_SECONDS`（内置定时模式间隔）
- `RUN_MODE`（`once` / `loop`）
- `ALIYUN_REGION`
- `SECURITY_GROUPS`（单账号多目标）
- `ACCOUNTS`（多账号配置）
- `RULE_IDENTIFIER`（规则 ID，当前固定）
- `IP_SOURCES`（多个源）
- `ACCESS_KEY_ID` / `ACCESS_KEY_SECRET`（仅环境变量注入）
- `ALERT_WEBHOOK_URL`
- `ALERT_RATE_LIMIT_SECONDS`

## 6. Error Handling Strategy
- IP 源请求失败：记录并继续尝试其他源。
- 多源全部不可用/全不一致：本轮终止，不调用更新。
- 阿里云更新失败：有限重试后仍失败则记录错误并退出。
- 所有错误日志必须脱敏，禁止输出密钥。

## 7. Security Considerations
- 凭证不写入代码或日志。
- 日志中不输出完整凭证与敏感请求头。
- 仅最小权限访问目标安全组相关 API。

## 8. Open Questions
- 多账号配置格式采用 JSON 字符串环境变量还是外部配置文件。
- 多安全组更新策略默认顺序执行还是可选并发执行。
- 告警去重 key 设计（按账号+安全组+错误码聚合）。
