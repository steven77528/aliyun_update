# AGENTS.md

This file provides guidance to agents when working with code in this repository.

- 架构讨论应以 OpenSpec 工件流转为中心，而非服务/模块部署拓扑；仓库仅见规范目录 [`openspec/`](openspec/)。
- 约束是 schema 固化：`spec-driven`（[`openspec/config.yaml:1`](openspec/config.yaml:1)），方案输出应覆盖 proposal/design/tasks 的依赖关系。
- 现有变更 [`openspec/changes/timer_check_update/requirement.md`](openspec/changes/timer_check_update/requirement.md) 为空，任何架构决策都应先定义需求边界再细化设计。
- 未发现构建、lint、测试入口；架构验收标准应写成可执行的 OpenSpec 任务与验收条目，而非 CI 命令。

