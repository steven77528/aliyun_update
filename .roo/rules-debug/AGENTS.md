# AGENTS.md

This file provides guidance to agents when working with code in this repository.

- 当前仓库未包含可运行应用或测试目标；调试重点应是 OpenSpec 变更工件完整性，而非运行时问题。
- 可用排查命令以 OpenSpec CLI 为主：`openspec list --json`、`openspec status --change "<name>" --json`、`openspec instructions <artifact> --change "<name>" --json`。
- [`openspec/changes/timer_check_update/requirement.md`](openspec/changes/timer_check_update/requirement.md) 当前为空；若遇“无法实现/无法验证”先确认为需求缺失，而非代码故障。
- 仓库不存在测试框架与测试目录；不要用“跑单测”定位问题。

