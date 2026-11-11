# timer-check-update 使用说明（扩展版）

## 1. 脚本位置
- [`openspec/changes/timer-check-update/implementation/src/ip_sync.py`](openspec/changes/timer-check-update/implementation/src/ip_sync.py)

## 2. 运行前环境变量

### 2.1 运行模式
- `RUN_MODE=once|loop`（默认 `once`）
- `CHECK_INTERVAL_SECONDS`（`RUN_MODE=loop` 时生效）

### 2.2 账号与目标配置

方式 A：单账号（向后兼容）

- `ALIYUN_REGION`
- `SECURITY_GROUP_ID`
- `RULE_IDENTIFIER`（规则 ID）
- `ACCESS_KEY_ID`
- `ACCESS_KEY_SECRET`

方式 B：单账号多目标

- `SECURITY_GROUPS`（JSON 数组，元素含 `security_group_id`/`rule_identifier`）

方式 C：多账号

- `ACCOUNTS`（JSON 数组，元素含 `name`/`region_id`/`access_key_id`/`access_key_secret`/`security_groups[]`）

### 2.3 可选参数

- `IP_SOURCES`（逗号分隔；为空则使用内置多源）
- `STATE_FILE`（默认 `./.ip_sync_state.json`）
- `ALERT_STATE_FILE`（默认 `./.ip_sync_alert_state.json`）
- `LOCK_FILE`（默认 `./.ip_sync.lock`）
- `REQUEST_TIMEOUT_SECONDS`（默认 `6`）
- `RETRY_COUNT`（默认 `2`）
- `RETRY_BACKOFF_SECONDS`（默认 `1.0`）
- `ALERT_WEBHOOK_URL`（为空则不发送告警）
- `ALERT_RATE_LIMIT_SECONDS`（默认 `300`）

## 3. 单次执行
```bash
python3 openspec/changes/timer-check-update/implementation/src/ip_sync.py --once
```

## 4. 内置定时执行
```bash
RUN_MODE=loop CHECK_INTERVAL_SECONDS=3600 python3 openspec/changes/timer-check-update/implementation/src/ip_sync.py --loop
```

## 5. cron 调度示例
每小时执行一次（单次模式示例）：
```cron
0 * * * * /usr/bin/python3 /path/to/repo/openspec/changes/timer-check-update/implementation/src/ip_sync.py --once >> /var/log/ip-sync.log 2>&1
```

## 6. 常见退出码
- `0`：成功（包括 IP 未变化时跳过更新）
- `10`：所有 IP 源不可用
- `11`：多源结果不一致（无多数）
- `20`：存在至少一个目标更新失败（重试后仍失败）
- `30`：配置错误（缺少必填环境变量等）
- `40`：已有实例执行中（锁冲突）

## 7. 自动化测试
```bash
python3 -m unittest discover -s openspec/changes/timer-check-update/implementation/tests -p 'test_*.py'
```

## 8. 常见问题
1. `sdk_import_failed`：未安装阿里云 Python SDK。
2. `api_error`：凭证/权限/规则 ID 或区域不匹配，请核对最小权限与参数。
3. `ip.resolve.inconsistent`：公网 IP 源返回不一致，本轮按设计不更新。
4. 需要告警时请配置 `ALERT_WEBHOOK_URL`，并根据场景调整 `ALERT_RATE_LIMIT_SECONDS`。
