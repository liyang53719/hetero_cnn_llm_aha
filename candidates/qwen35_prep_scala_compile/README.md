# Qwen3.5 Prep Scala compile-only 源码与状态摘录

状态：源码/状态摘录已封板；实际终态复核为 `PASS_ACTUAL_QWEN35_PREP_SCALA_COMPILE_ONLY`。

## 包的边界

这是小型、可审阅的源码/状态摘录，不是完整可执行 closure。包内不含 Scala 输入、工具二进制、完整冻结计划、原始运行收据或日志；原 launcher 不能直接运行。

- `launch_compile.py`、`run_compile.py` 逐字节复制自冻结 runner r2，没有路径替换或行为修改。
- `INPUT_PINS.json` 从既有小型 JSON 库存提取 18 个 Scala 源（111435 bytes）、314 个工具（296950644 bytes）、87 个 classpath JAR（61870159 bytes）以及 6 个原监督器辅助输入的 bytes/SHA-256。所有标识均为相对逻辑命名空间，不是原机器路径；源与工具本体均不在包中。87 JAR 是 314 工具的子集，不应重复相加。
- `REPRODUCE_COMMAND.txt` 仅展示编译器 argv 的显式变量模板与原 18 源顺序，不是新的 builder，不会自动寻找依赖或改写路径，也不提供原监督或资源限制的等价复现。
- `SUMMARY.json` 保存有限状态结论与实际复核 pin；不会因编译通过而提升到硬件行为通过。
- `MANIFEST.json` 校验其余七个公开文件，自身不自哈希；外部报告需另行固定 MANIFEST 的 SHA-256。
- `ALLOWLIST.json` 是精确公开文件边界，不应递归发布其父目录。

## 已复核的有限实际结果

唯一实际尝试已复核为自然退出 0，输出 `PASS_QWEN35_PREP_SCALA_COMPILE_ONLY`，89 个 class 文件（843199 bytes），4 个预期 Prep 类均在，338 个冻结输入的 before/after 一致。stdout elapsed 为 31.116176181996707 秒，这是 launcher 内部单调时钟计时，不是独立外层 wall-time 测量。

最终实际 review 的 pin：22125 bytes，SHA-256 `681d3b16acd0d2c1e4b9afe478b5da1a66a13094c05384710992a1c717a47708`。这里只提供必要结论和摘要 pin，不包含 private review 原文；pin 不是完整证据已经公开的证明。

终态复核的子进程 WNOWAIT 观测为 `code=1/status=0`，随后已回收、进程组 absent、cleanup confirmed、无 timeout。`kill_attempted=true` 表示原监督器在观测自然退出后进行进程组清理，不能单独解释成编译被强杀，也不能删掉这一事实以美化状态。

本次通过仅是 Scala 编译限定：不是 Chisel 构造/展开，不是 RTL，不是 ACK/握手、数值、token 调度或 M128 验证。五个 RTL 目标仍为 0/5；旧 Qwen2 完整 run 的执行状态与清理状态仍为 UNKNOWN。本包不继承旧 pass。

## 为什么不能直接运行原 launcher

原 `launch_compile.py` 固定要求 CPython 3.12.14 和隔离解释器标志，并逐字节校验一个被明确排除的机器冻结计划 `FROZEN_PLAN.json`（177190 bytes，SHA-256 `9ae7e095739795338bb22521d6bbd70910ff75c9af98398ea82649a0c064a984`）。该计划含机器路径与原运行边界，不能公开。它还引用外部监督器与其他未打包输入。

因此两份源码是原实现的审阅材料，不是开箱即用的命令。相对 pins 只帮助接收方独立取得与校验输入；仍需独立重建并冻结依赖与监督配置，不能把重建的方案冒称为原冻结计划。模板的直接 Java 命令不执行原 Python 监督器，因而不重现原 180 秒全局期限、150 秒工作期限、清理/回收协议、资源及输出边界。独立运行需另行建立这些保障，且不得宣称与本次实际结果同一资格。

源码中的 `/tmp`、`/proc` 与 `/proc/meminfo` 是通用 Linux 接口常量，保留原字节，不属于机器特定私有路径。

## 摘录制作验证

制作过程仅读取两份 Python 源和已有小型 JSON，复制并校验源字节，进行静态 Python AST/代码对象语法检查、JSON 结构与相对路径检查。没有 import/exec 候选源码，没有运行 Scala/JVM、候选测试、Chisel 或硬件入口，没有再次读取或哈希约 297 MB 的工具二进制，没有改写冻结源、实际输出或仓库，也没有 push。

未公开的内容包括：机器私有绝对路径、FROZEN_PLAN 原文、原始日志/收据、数组/权重、工具二进制、class 文件和其他运行产物。摘要和摘要 pin 不等于原始证据全部公开。
