# Design: format-config-and-logging

## 1. Goals
- 落地三段配置模型：基础配置（JSON）、阿里云配置（YAML）、通知配置（JSON）。
- 支持阿里云配置的多账号/多安全组/多规则层级，并要求规则展示名（`name/alias`）贯穿日志与邮件展示。
- 统一日志输出模板、按天分割与保留清理策略，满足可读与可检索要求。
- 明确目录规范与 Docker 交付规范，形成可复现部署方式。

## 2. Non-goals
- 不改变核心业务目标与主流程语义（IP 检测、比对、更新）。
- 不新增非邮件通知渠道。
- 不引入外部日志平台。

## 3. Architecture Overview
```text
Config Layer
  ├─ base.json
  ├─ notify.json
  └─ aliyun.yaml
         │
         ▼
Validation + Normalize
         │
         ▼
run_cycle
  ├─ step1 获取公网IP
  ├─ step2 比较IP
  ├─ step3 更新安全组规则
  └─ step4 发送通知
         │
         ├─ structured log (daily file)
          └─ notification payload (含 rule_name/alias)
```

## 4. Configuration Design

### 4.1 BaseConfig (JSON)
- `check_interval_seconds`: 检查间隔
- `log_retention_days`: 日志保留天数（默认 7）
- `ip_sources`: 公网 IP 来源列表

### 4.2 AliyunConfig (YAML)
层级结构：
```text
accounts[]
  └─ security_groups[]
      └─ rules[]
          ├─ rule_id (required)
          ├─ alias or name (required, 用于展示)
          ├─ region (optional/按现有能力)
          └─ cidr_or_ip
```

约束：
- 每个 account 至少 1 个 security_group。
- 每个 security_group 至少 1 条 rule。
- `alias/name` 至少其一必填，作为日志与邮件展示主键。

### 4.3 NotifyConfig (JSON)
- `enabled`
- `smtp_host`
- `smtp_port`
- `smtp_username`
- `smtp_password`
- `smtp_use_tls`
- `email_from`
- `email_to`（数组或逗号分隔字符串，规范化为数组）

## 5. Config Loading & Validation
- 启动阶段按固定顺序读取：base.json → aliyun.yaml → notify.json。
- 校验失败输出脱敏摘要，禁止输出密钥、密码、原始敏感值。
- 对可选字段提供默认值（如 `log_retention_days=7`）。

## 6. Logging Design

### 6.1 Log Template
- 开始边界：`----------------------开始任务----------------------`
- `step1`: 获取公网 IP（按来源记录 URL、结果、耗时）
- `step2`: 比较当前/历史 IP 与是否变化
- `step3`: 逐条更新规则，输出安全组 ID、规则 ID、规则 `name/alias`、结果、耗时
- `step4`: 发送通知，输出通知目标、结果、耗时
- 结束边界：`----------------------完成任务，总耗时: xxxms----------------------`

### 6.2 Redaction & White-list
只允许以下类型字段：
- 时间、级别、步骤名、对象标识、规则标识、规则名称、结果、耗时、错误摘要。

禁止：
- AccessKey/Secret、SMTP 密码、完整堆栈、过细调试明细。

### 6.3 File Rotation & Retention
- 日志文件命名：`ip_sync_YYYYMMDD.log`。
- 每次执行前或结束后触发清理：删除超过 `log_retention_days` 的日志文件。

## 7. Notification Content Alignment
- step4 通知内容与 step3 字段保持一致，确保邮件可直接映射到日志：
  - account/security_group/rule_id/rule_name_or_alias/result/duration

## 8. Directory Standardization
- 脚本目录：`src/`
- 测试目录：`tests/`
- 产物目录：`target/`

兼容策略：
- 若当前测试位于 `src/tests/`，通过迁移或映射方式对齐到 `tests/` 规范，并在文档中说明。

## 9. Docker Delivery Design
- Dockerfile：安装 Python 与依赖、设置工作目录、读取环境变量。
- docker-compose.yml：定义服务、镜像、环境变量、卷挂载。
- 挂载目录规范：
  - 宿主 `./config` ↔ 容器 `/app/config`
  - 宿主 `./data` ↔ 容器 `/app/data`
  - 宿主 `./logs` ↔ 容器 `/app/logs`
- 镜像压缩包产物输出到 `target/`，用于离线加载部署。

## 10. Testing Strategy
- 配置测试：JSON/YAML 解析、层级校验、展示名字段（name/alias）校验与脱敏错误。
- 日志测试：step 模板、规则展示名输出、命名与保留清理。
- 通知测试：邮件内容包含规则展示名与结果字段，不泄露敏感信息。
- 容器测试：Dockerfile 构建与 compose 挂载生效。

## 11. Open Questions
- `email_to` 的输入格式最终是否统一为数组。
- `tests` 目录重构采用“立即迁移”还是“阶段兼容”。
- 错误日志摘要粒度（兼顾脱敏与排障效率）的最终口径。
