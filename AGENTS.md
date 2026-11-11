# AGENTS.md

This file provides guidance to agents when working with code in this repository.

- 当前仓库是一个精简 OpenSpec 工作区，不是应用代码仓；核心配置仅见 [`openspec/config.yaml`](openspec/config.yaml)。
- OpenSpec schema 固定为 `spec-driven`（[`openspec/config.yaml:1`](openspec/config.yaml:1)），变更流程应围绕 proposal/design/tasks。
- 未发现 `package.json`/`pyproject.toml`/`Makefile` 等构建入口；不要假设存在 build/lint/test 脚本。
- 单测命令：当前仓库未配置测试框架或测试目录，无法运行“单个测试”；仅可执行 OpenSpec CLI 工作流命令。
- 可用且已在仓库技能文档中出现的命令模式：`openspec list --json`、`openspec status --change "<name>" --json`、`openspec instructions <artifact> --change "<name>" --json`（参见 [`.codex/skills/openspec-propose/SKILL.md`](.codex/skills/openspec-propose/SKILL.md)、[`.codex/skills/openspec-apply-change/SKILL.md`](.codex/skills/openspec-apply-change/SKILL.md)）。
- 代码风格配置几乎为空：[`openspec/config.yaml`](openspec/config.yaml) 仅含注释示例，无强制 import/format/type/naming 规则；新增内容应保持最小改动并遵循现有 Markdown 风格。
- 变更目录中 [`openspec/changes/timer_check_update/requirement.md`](openspec/changes/timer_check_update/requirement.md) 当前为空；实现前需先补齐需求与任务，不要直接假设业务细节。
- AI 规则文件现状：未发现 `CLAUDE.md`、`.cursorrules`、`.cursor/rules/`、`.github/copilot-instructions.md`、`.roorules`。

