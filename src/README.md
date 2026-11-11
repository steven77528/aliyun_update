# 使用说明（IP 同步）

## 配置方式（三文件）

推荐使用三份配置文件：

- 基础配置：`config/base.json`
- 云厂商配置：`config/cloud.yaml`
- 通知配置：`config/notify.json`

通过环境变量指定入口：

```dotenv
BASE_CONFIG_FILE=./config/base.json
CLOUD_CONFIG_FILE=./config/cloud.yaml
NOTIFY_CONFIG_FILE=./config/notify.json
```

兼容说明：

- 仍兼容旧变量 `ALIYUN_CONFIG_FILE`
- 仍兼容仅阿里云的旧 `accounts:` YAML 结构
- 仍兼容单账号环境变量模式

## 脚本结构（模块化后）

当前入口仍为 `ip_sync.py`，核心逻辑拆分到 `ip_sync_app/`：

- `ip_sync_app/config_loader.py`：配置读取、环境变量兼容、YAML/JSON 解析
- `ip_sync_app/ip_service.py`：公网 IP 获取与多数投票判定
- `ip_sync_app/sg_service.py`：阿里云/华为云安全组规则更新与重试
- `ip_sync_app/notification_service.py`：SMTP 汇总通知、夜间缓冲、Webhook 告警
- `ip_sync_app/log_service.py`：日志输出、脱敏、按天落盘与保留策略
- `ip_sync_app/orchestrator.py`：主流程编排、锁控制、单次/循环执行入口
- `ip_sync_app/state_service.py`：状态文件、告警状态、通知缓冲持久化

## 云厂商配置（YAML）

推荐通过 `CLOUD_CONFIG_FILE` 指向统一 YAML 配置文件，支持阿里云与华为云并行配置：

```yaml
aliyun:
  - account: "阿里云账号"
    region_id: "cn-hangzhou"
    access_key_id: "your_access_key_id"
    access_key_secret: "your_access_key_secret"
    security_groups:
      - security_group_id: "sg-12345678"
        alias: "办公网入口"
        rules:
          - rule_id: "sgr-12345678"
            alias: "SSH 规则"

huawei:
  - account: "华为云账号"
    region_id: "cn-north-4"
    access_key_id: "your_access_key_id"
    access_key_secret: "your_access_key_secret"
    security_groups:
      - security_group_id: "sg-abcdefgh"
        alias: "办公网入口"
        rules:
          - rule_id: "rule-abcdefgh"
            alias: "SSH 规则"
```

说明：

- `alias/name` 会展示在日志与通知中
- 阿里云仍走“按规则 ID 修改来源 CIDR”
- 华为云走“查询旧规则 -> 创建新规则 -> 删除旧规则”的替换流程

## 基础配置（JSON）

`config/base.json` 示例：

```json
{
  "check_interval_seconds": 3600,
  "log_retention_days": 7,
  "ip_sources": [
    "https://api64.ipify.org",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com"
  ]
}
```

## SMTP 汇总通知配置（JSON）

`config/notify.json` 核心字段：

- `enabled`
- `smtp_host` / `smtp_port` / `smtp_username` / `smtp_password`
- `smtp_use_tls`
- `email_from` / `email_to`
- `retry_count` / `rate_limit_seconds`
- `pending_file`

## 通知行为

- 当本轮存在安全组更新尝试时，发送 1 封汇总邮件
- 通知明细包含云厂商、账号、区域、安全组、规则、旧 IP、新 IP、结果、失败原因
- 邮件主题固定为 `[云安全组自动更新] ---- 更新通知`
- 夜间窗口 `22:00-07:00` 仅缓冲不发送，07:00 后统一发送

## Step3 日志示例

```text
${timestamp}-INFO: step3：更新安全组规则
${timestamp}-INFO: step3.1：目标安全组：阿里云 | account-a | cn-hangzhou | 办公网入口 | SSH 规则
${timestamp}-INFO: 当前ip地址: 125.119.208.195，之前记录的ip地址: 1.1.1.1，是否发生变化: True，开始更新安全组规则
${timestamp}-INFO: 更新结果: 成功，耗时: 391ms
${timestamp}-INFO: step3.2：目标安全组：华为云 | account-b | cn-north-4 | 办公网入口 | SSH 规则
${timestamp}-INFO: 当前ip地址: 125.119.208.195，之前记录的ip地址: 125.119.208.195，是否发生变化: False，跳过更新安全组规则
```

## Docker 构建与运行

镜像内会安装以下 Python 依赖：

- 阿里云：`aliyun-python-sdk-core`、`aliyun-python-sdk-ecs`
- 华为云：`huaweicloudsdkcore`、`huaweicloudsdkvpc`
- 配置解析：`pyyaml`

1. 构建镜像

```bash
docker compose -f docker-compose.yml build
```

2. 单次执行

```bash
docker compose -f docker-compose.yml up --abort-on-container-exit
```

3. 导出镜像到 `target/`

```bash
mkdir -p ../target && docker save timer-check-update-ip-sync:latest -o ../target/ip-sync_latest.tar
```
