# 验收清单（对应 proposal 成功标准）

关联文档：[`openspec/changes/timer-check-update/proposal.md`](openspec/changes/timer-check-update/proposal.md)

## S1. IP 未变化时不调用更新 API
- 方法：首次执行写入状态后，再次执行且返回相同 IP，观察日志事件为 `run.skip_update`。
- 当前状态：⚠️ 待外部环境验证（需可用的 IP 源与运行环境）。

## S2. IP 变化后一个周期内更新成功并记录日志
- 方法：构造“上次 IP 与当前 IP 不一致”场景，校验日志包含 `aliyun.update.success`。
- 当前状态：⚠️ 待外部环境验证（需要有效阿里云凭证与可操作规则 ID）。

## S3. IP 获取失败或 API 失败时可诊断且不泄露密钥
- 方法：
  1) 配置无效 IP 源，期望退出码 `10/11` 与错误日志；
  2) 配置错误凭证，期望退出码 `20` 与 `api_error`；
  3) 检查日志中 `ACCESS_KEY_ID` 脱敏输出。
- 当前状态：🟡 部分完成（代码路径已实现，需联调确认完整行为）。

## S4. 通过配置调整检查参数，无需改代码
- 方法：改动环境变量（如 `IP_SOURCES`、`RETRY_COUNT`、`STATE_FILE`），运行行为发生对应变化。
- 当前状态：✅ 已完成（配置读取逻辑已实现于 [`openspec/changes/timer-check-update/implementation/src/ip_sync.py`](openspec/changes/timer-check-update/implementation/src/ip_sync.py)）。

## S5. 可通过命令触发单次检查
- 方法：执行 `python3 .../ip_sync.py --once`。
- 当前状态：✅ 已完成（脚本入口已实现，且通过 `py_compile` 语法校验）。

## 本地已执行校验
- `python3 -m py_compile openspec/changes/timer-check-update/implementation/src/ip_sync.py` 通过。

## 阻塞项
- 缺少可用阿里云真实环境（凭证、目标安全组、规则 ID），无法在当前会话内完成 S1/S2/S3 的端到端实测闭环。
