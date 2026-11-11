## Why

当前脚本仅支持阿里云安全组规则更新，无法覆盖华为云环境。已有需求文档明确提出需要支持华为云安全组规则在公网 IP 变化时自动更新，且要求与现有阿里云能力并行共存。

## What Changes

- 新增华为云安全组规则更新能力，在公网 IP 变化时同步处理华为云目标规则。
- 将云厂商配置从单一 `aliyun.yaml` 扩展为统一的 `cloud.yaml`，支持阿里云与华为云并行配置。
- 扩展运行日志与通知内容，增加云厂商字段，便于区分阿里云与华为云更新记录。
- 保持现有阿里云能力不变，并兼容旧的 `ALIYUN_CONFIG_FILE` 配置入口。

## Capabilities

### New Capabilities

- `cloud-provider-support`: 支持在同一轮公网 IP 变化处理中更新华为云安全组规则。

### Modified Capabilities

- `config-layering`: 支持统一云配置文件，同时包含阿里云与华为云账号、区域、安全组、规则层级。
- `notification-readability`: 通知内容增加云厂商字段，能够区分不同云厂商的规则更新结果。
- `log-standardization`: step3 日志支持展示云厂商维度，不再限定为阿里云。

## Impact

- 受影响模块：配置解析、规则更新服务、主流程编排、日志输出、通知内容、README 与示例配置。
- 受影响依赖：新增华为云 Python SDK 依赖；华为云规则更新将采用“查询旧规则 -> 创建新规则 -> 删除旧规则”的替换流程。
