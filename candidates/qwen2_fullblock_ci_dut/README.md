# CI 完整 block 接线候选（尚未实际运行）

仅用于 Qwen2-1.5B 单个完整 block、M128 的新 CI 接线。当前没有本包数值 PASS、RTL PASS 或新利用率实测。

- 输入沿已发布的固定来源与转换；参考沿官方 AST 数学。在同次 CI 本地逐项核对既有 29 输出期望后建立新的 `FROZEN_BINDING`，不改 bootstrap 原始状态。
- 新绑定 SHA 由 launcher 传入独立实际进程；核输入、参考、严格 native 编译产物、当前 Python/libpython 和源码边界。
- 原完整 block driver 数值主体不改；tail 与已发布原始文件逐字节相同。保留精确 raw/typed/oracle 访问和完整完成协议。
- 新 CI 的 NumPy/PyYAML 在依赖与 payload audit 安装前按固定来源初始化，仅两个精确包根文件显式归类为运行库，其余文件仍沿原分类器；安装后仍拒未列出的 work 文件与 lazy imports。新增 PyYAML 官方 wheel 单独按 hash 安装。
- 3300/3330 秒仅沿已授权工程预算；实际工作流启动仍需新源码、平台、输入/参考与资源独审通过。

冷测使用显式模块名（命名空间目录不支持 `unittest discover -t .`）：

```sh
mods=$(find candidates/qwen2_fullblock_ci_dut -maxdepth 1 -name 'test_*.py' | sed 's,/,.,g;s/\.py$//' | sort | tr '\n' ' ')
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest $mods -q
PYTHONDONTWRITEBYTECODE=1 python -B -O -m unittest $mods -q
```

当前 89 项普通和优化冷测通过；均非完整业务数值运行。新工作流保持单次 75 分钟上限；仅在独立外部 review 文件与精确源码闭包齐备后启动。允许的结果出口限固定安全聚合；不得外传逐 tensor 元数据、详细私有日志或可重建权重。
