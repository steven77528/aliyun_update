# 系统信息
当前系统为 macOS，终端配置为 zsh，使用的 shell 工具为 oh-my-zsh，编辑器为 VSCode。

## 规则补充

1. 本仓库为 OpenSpec 工作区，按 `spec-driven` 流程执行，核心配置见 `openspec/config.yaml`。
2. 需求或变更应围绕 `proposal.md`、`design.md`、`tasks.md` 维护，不直接跳过工件编写实现业务代码。
3. 当前仓库未配置常规构建/测试入口（如 `package.json`、`pyproject.toml`、`Makefile`），不要假设存在 `npm test`、`pytest` 等命令。
4. 若使用 OpenSpec CLI，优先采用以下命令模式：
   - `openspec list --json`
   - `openspec status --change "<name>" --json`
   - `openspec instructions <artifact> --change "<name>" --json`
5. 新增文档遵循最小改动原则，保持现有 Markdown 风格与术语一致。
