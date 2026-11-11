# tests 目录说明

当前项目测试实现位于 `src/tests/`，用于兼容既有执行命令：

```bash
python3 -m unittest discover -s src/tests -p 'test_*.py'
```

本目录用于满足“测试位于 tests 目录”的交付结构约定。
后续如需彻底迁移，可将 `src/tests/` 迁移至本目录并同步更新执行命令。
