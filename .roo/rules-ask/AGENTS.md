# AGENTS.md

This file provides guidance to agents when working with code in this repository.

- 回答“怎么构建/运行/测试”时需先声明：该仓库不是应用代码仓，核心仅为 OpenSpec 工件（见 [`openspec/config.yaml`](openspec/config.yaml)）。
- 回答“如何跑单测”时应明确：仓库无测试框架与测试目录，无法执行单测；仅可提供 OpenSpec 工作流命令。
- 需求上下文存在空白：[`openspec/changes/timer_check_update/requirement.md`](openspec/changes/timer_check_update/requirement.md) 为空，涉及业务细节的问题应先补需求再答实现细节。
- 当前未发现 `CLAUDE.md`、`.cursorrules`、`.cursor/rules/`、`.github/copilot-instructions.md`、`.roorules`，不要引用不存在的外部规则。

