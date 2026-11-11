# 实际测试操作步骤

本文档用于从本地单元测试推进到真实云资源验证。所有真实云测试都应先使用低风险测试安全组规则，不要直接拿生产 SSH/RDP/数据库入口规则做首轮验证。

## 1. 测试前准备

确认当前 Python 环境：

```powershell
python -c "import sys; print(sys.executable)"
python -c "import yaml; print(yaml.__version__)"
```

如需在本地直接调用云 API，安装运行依赖：

```powershell
python -m pip install PyYAML aliyun-python-sdk-core aliyun-python-sdk-ecs huaweicloudsdkcore huaweicloudsdkvpc
```

先跑单元测试，确认基础逻辑正常：

```powershell
python -m unittest discover -s src/tests -p test_*.py
```

期望结果：

```text
Ran 25 tests
OK
```

## 2. 准备真实云测试规则

在云控制台准备一条专门用于测试的安全组入方向规则：

- 规则用途：例如临时 SSH 22、临时 HTTP 8080，或只用于验证的低风险端口。
- 初始来源 CIDR：可先填一个非当前公网 IP，例如 `1.1.1.1/32`。
- 记录回滚信息：云厂商、账号、区域、安全组 ID、规则 ID、原始来源 CIDR、协议、端口、描述。
- 凭据权限：只授予读取安全组、修改安全组规则所需权限。

华为云需要额外注意：当前实现采用”查询旧规则 -> 创建新规则 -> 删除旧规则”的替换流程。每次更新后云端会生成新的规则 ID，但**配置文件里的 `rule_id` 应始终保持首次填入的原始值，不需要手动回填**。程序会通过状态文件自动追踪最新的实际规则 ID，下次执行时直接使用状态文件中记录的 ID 操作云端规则。如果手动修改了配置里的 `rule_id`，状态文件的 key 会跟着变化，导致历史 IP 记录丢失，下次会误判为 IP 发生变化并再次触发更新。

## 3. 创建本地测试配置

从仓库根目录执行：

```powershell
New-Item -ItemType Directory -Force .tmp\runtime | Out-Null
Copy-Item src\config\base.json .tmp\runtime\base-test.json -Force
Copy-Item src\config\cloud.yaml .tmp\runtime\cloud-test.yaml -Force
Copy-Item src\config\notify.json .tmp\runtime\notify-test.json -Force
```

编辑 `.tmp\runtime\cloud-test.yaml`：

- 只保留本次要测试的云厂商块，例如只测阿里云就删除或注释 `huawei:`。
- 填入真实 `account`、`region_id`、`access_key_id`、`access_key_secret`。
- 填入测试安全组的 `security_group_id` 和测试规则的 `rule_id`。
- `alias` 用于日志和邮件展示，建议填清楚。

如暂不测试邮件，编辑 `.tmp\runtime\notify-test.json`，设置：

```json
{
  "enabled": false
}
```

也可以保留完整 JSON，只把 `enabled` 改为 `false`。

## 4. 单次真实更新测试

从仓库根目录设置环境变量：

```powershell
$runtime = (Resolve-Path ".tmp\runtime").Path
$env:RUN_MODE = "once"
$env:BASE_CONFIG_FILE = Join-Path $runtime "base-test.json"
$env:CLOUD_CONFIG_FILE = Join-Path $runtime "cloud-test.yaml"
$env:NOTIFY_CONFIG_FILE = Join-Path $runtime "notify-test.json"
$env:STATE_FILE = Join-Path $runtime "ip_sync_state.json"
$env:ALERT_STATE_FILE = Join-Path $runtime "ip_sync_alert_state.json"
$env:LOCK_FILE = Join-Path $runtime "ip_sync.lock"
$env:LOG_DIR = Join-Path $runtime "logs"
```

执行一次：

```powershell
python .\src\ip_sync.py --once
$LASTEXITCODE
```

期望退出码：

- `0`：执行成功。
- `10`：所有公网 IP 源失败。
- `11`：公网 IP 源结果不一致，未形成多数。
- `20`：云规则更新失败。
- `30`：配置错误。
- `40`：已有实例持有锁。

如果退出码是 `11`，先查看日志中的各 IP 源返回值：

```powershell
Get-Content .tmp\runtime\logs\ip_sync_*.log -Tail 80
```

常见原因是部分源返回 IPv6，部分源返回 IPv4，或不同出口链路返回不同地址。实际测试时应先把 `.tmp\runtime\base-test.json` 的 `ip_sources` 收敛到 2-3 个会返回同一个公网 IP 的源，例如：

```json
{
  "check_interval_seconds": 60,
  "log_retention_days": 7,
  "ip_sources": [
    "https://checkip.amazonaws.com",
    "https://api.ipify.org",
    "https://ipinfo.io/ip"
  ]
}
```

修改后重新执行第四步。只有形成多数共识后，程序才会进入 step2/step3 并调用云 API。

期望日志包含：

```text
step1：获取当前公网ip
step2：比较当前ip地址与之前记录的ip地址
step3：更新安全组规则
step3.1：目标安全组：...
是否发生变化: True，开始更新安全组规则
更新结果: 成功
```

检查状态文件：

```powershell
Get-Content .tmp\runtime\ip_sync_state.json -Raw
```

检查云控制台：

- 阿里云：目标规则的来源 CIDR 应变为当前公网 IP 的 `/32`。
- 华为云：应创建出来源 CIDR 为当前公网 IP `/32` 的新规则，并删除旧规则。配置文件里的 `rule_id` 保持原始值不变，程序会自动追踪新规则 ID。

如果日志显示 `更新结果: 失败`，先打开结构化日志重新执行一次，获取云 SDK 返回的错误摘要：

```powershell
$env:LOG_VERBOSE_STRUCTURED = "true"
python .\src\ip_sync.py --once
Get-Content .tmp\runtime\logs\ip_sync_*.log -Tail 120
```

华为云常见失败：

- `Incorrect IAM authentication information: Unauthorized`：`access_key_id/access_key_secret` 不是有效 AK/SK，或 AK/SK 不属于当前账号/区域项目。`access_key_id` 需要填写访问密钥 ID，不是 IAM 用户名；`access_key_secret` 需要填写对应的 Secret Access Key，不是登录密码。
- `rule_not_found:<rule_id>`：配置中的 `rule_id` 不存在，或华为云上一次替换成功后生成了新规则 ID，但配置仍是旧规则 ID。
- `CreateSecurityGroupRuleOption.__init__() got an unexpected keyword argument 'port_range_min'`：本地代码与当前华为云 SDK 字段不兼容。当前 SDK 使用 `multiport` 表示端口，代码需要复制旧规则的 `multiport`，不要传 `port_range_min/port_range_max`。
- 权限不足：用于测试的 IAM 用户需要具备查询安全组、创建安全组规则、删除安全组规则的权限。
- 区域不匹配：`region_id` 必须与安全组所在区域一致，例如上海一区通常是 `cn-east-3`。

定位前建议把 `.tmp\runtime\notify-test.json` 的 `enabled` 临时改为 `false`，避免失败重试期间反复发送通知邮件。

## 5. 幂等跳过测试

在不修改状态文件、不改变网络出口 IP 的情况下，再执行一次：

```powershell
python .\src\ip_sync.py --once
$LASTEXITCODE
```

期望结果：

- 退出码为 `0`。
- 日志出现 `是否发生变化: False，跳过更新安全组规则`。
- 云控制台中规则不应再次变化。

如需要再次触发真实更新分支，可以删除状态文件后重跑：

```powershell
Remove-Item .tmp\runtime\ip_sync_state.json
python .\src\ip_sync.py --once
```

这会再次调用云 API，请只对测试规则执行。

## 6. 邮件通知测试

编辑 `.tmp\runtime\notify-test.json`，填入真实 SMTP 配置：

```json
{
  "enabled": true,
  "smtp_host": "smtp.example.com",
  "smtp_port": 465,
  "smtp_username": "user@example.com",
  "smtp_password": "password",
  "smtp_use_tls": true,
  "email_from": "user@example.com",
  "email_to": ["receiver@example.com"],
  "retry_count": 3,
  "rate_limit_seconds": 1,
  "pending_file": ".tmp/runtime/ip_sync_notify_pending.json"
}
```

如要在真实云测试后单独验证邮件，先确认测试规则当前来源 CIDR 已经是本机公网 IP，然后删除测试状态文件触发一次通知：

```powershell
Remove-Item .tmp\runtime\ip_sync_state.json -ErrorAction SilentlyContinue
python .\src\ip_sync.py --once
```

程序会先查询云端规则。如果云端规则已经是当前 IP，应补回状态并发送通知，不应创建重复规则。

期望结果：

- 白天 `07:00-22:00`：日志出现 `step4：发送变更通知` 和 `汇总通知结果: 成功`。
- 夜间 `22:00-07:00`：邮件不会立即发送，日志应显示通知被缓冲，并写入 `pending_file`。
- 邮件内容应包含云厂商、账号、区域、安全组、规则、旧 IP、新 IP、结果。

## 7. Docker 运行测试

进入 `src` 目录：

```powershell
Set-Location .\src
```

创建或编辑 `.env`：

```dotenv
RUN_MODE=once
BASE_CONFIG_FILE=/app/config/base.json
CLOUD_CONFIG_FILE=/app/config/cloud.yaml
NOTIFY_CONFIG_FILE=/app/config/notify.json
STATE_FILE=/app/data/ip_sync_state.json
ALERT_STATE_FILE=/app/data/ip_sync_alert_state.json
LOCK_FILE=/app/data/ip_sync.lock
LOG_DIR=/app/logs
```

确认 `src/config/cloud.yaml` 已填入测试规则配置后，构建并运行：

```powershell
docker compose -f docker-compose.yml build
docker compose --env-file .env -f docker-compose.yml up --abort-on-container-exit
```

如果构建在 `FROM python:3.11-slim` 或基础镜像拉取阶段失败，并出现类似 `unable to fetch descriptor ... content size of zero`，说明 Docker Hub 上该浮动 tag 的元数据拉取异常。当前 Dockerfile 已固定为 `python:3.11-slim-bookworm`；也可以先手动验证：

```powershell
docker pull python:3.11-slim-bookworm
docker compose -f docker-compose.yml build
```

查看日志与状态：

```powershell
docker compose -f docker-compose.yml logs ip-sync
Get-Content .\data\ip_sync_state.json -Raw
```

如要测试循环模式，把 `.env` 中 `RUN_MODE=once` 改为：

```dotenv
RUN_MODE=loop
```

然后启动：

```powershell
docker compose --env-file .env -f docker-compose.yml up -d
docker compose -f docker-compose.yml logs -f ip-sync
```

停止：

```powershell
docker compose -f docker-compose.yml down
```

## 8. 验收清单

- 单元测试通过：`python -m unittest discover -s src/tests -p test_*.py`。
- 首次真实执行会把测试规则来源 CIDR 改成当前公网 IP `/32`。
- 第二次执行在 IP 未变时跳过更新。
- 状态文件按目标规则记录 `last_ip`。
- 日志文件写入 `$env:LOG_DIR` 指定目录。
- 邮件启用时，变更后能收到汇总通知；夜间能进入 pending 缓冲。
- Docker 镜像能构建，容器单次执行能完成。
- 华为云测试后配置文件 `rule_id` 保持原始值不变，状态文件已记录最新规则 ID。

## 9. 回滚步骤

如真实云测试结果不符合预期：

1. 到云控制台恢复测试规则的原始来源 CIDR。
2. 华为云如出现“新规则已创建但旧规则删除失败”，人工删除重复规则，保留符合预期的一条。
3. 删除本地测试状态，避免后续误判：

```powershell
Remove-Item .tmp\runtime\ip_sync_state.json -ErrorAction SilentlyContinue
Remove-Item .tmp\runtime\ip_sync_alert_state.json -ErrorAction SilentlyContinue
Remove-Item .tmp\runtime\ip_sync_notify_pending.json -ErrorAction SilentlyContinue
```

4. 重新执行单元测试，确认代码路径仍正常：

```powershell
python -m unittest discover -s src/tests -p test_*.py
```
