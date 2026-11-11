# AGENTS.md

This file provides guidance to agents when working with code in this repository.

- 本仓库不含应用源码与依赖清单；主要产物是 OpenSpec 文档，核心入口是 [`openspec/config.yaml`](openspec/config.yaml)。
- 仅确认 `spec-driven` 流程（[`openspec/config.yaml:1`](openspec/config.yaml:1)）；实现前应先补齐变更工件，不要直接编写业务代码。
- 当前变更 [`openspec/changes/timer_check_update/requirement.md`](openspec/changes/timer_check_update/requirement.md) 为空，属于未完成需求状态。
- 未发现可执行测试体系；“单测”不可运行，避免虚构 `npm test`/`pytest` 等命令。

