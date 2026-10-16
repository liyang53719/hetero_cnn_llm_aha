# U00.2 A-hold 解释执行首次运行：原始超时证据

结论：实际 Scala 编译和 CHIRRTL 结构检查成功，解释执行阶段在原定 240 秒上限终止。实际 owner 的握手执行尚未通过；本记录不改变完整 block 数值验收或 90% 有效 MAC 利用率验收状态。

## 原始运行与不可变归档

- 提交：`00d1d6540a2a8359adc7b64e86e5d30ad6cd678e`。
- [原始 CI run 38976754470](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38976754470)，attempt 1；job `117227926193`，结论 `failure`。
- artifact `12079995425`，ZIP 17,524 字节，SHA256 `664e58185552c968a84b3e8dc69b2f5a2215baf48922c86a6bbbb5cd7ef9a64a`。
- `candidates/qwen2_resident_matrix/dense_a_hold_interpreter_results/` 保存原始 `summary.json`、`source-sha256.json`、`dependency-sha256.json`、`diagnostic.txt` 四个成员的原字节。`manifest.json` 是后续核对记录，不是 CI 原始输出。
- 未提交 ZIP、CHIRRTL、class 文件、jar、波形或完整日志。归档校验器的 `PASS_IMMUTABLE_FAILURE_ARCHIVE` 仅表示失败归档完整，不能读成硬件执行通过。

## 已完成阶段和边界

| 阶段 | 原始状态 | 实际墙钟秒 | 原定上限秒 |
| --- | --- | ---: | ---: |
| 依赖准备 | PASS | 1.968 | 120 |
| 实际 Scala 编译 | PASS | 15.357 | 180 |
| owner/probe CHIRRTL 结构检查 | PASS | 3.928 | 30 |
| 单 case Treadle 解释执行 | TIMEOUT | 240.064 | 240 |

总墙钟 262.894 秒，Java `21.0.12.1`。总预算仍为 600 秒，JVM active processor 1、最大堆 2 GiB、栈 4 MiB；阶段超时不等于耗尽总预算，也没有证据证明 OOM 或 CPU/内存峰值。不会自动提高预算或重跑。

计划执行的是 reuse=true、M16/K32/N160 的 owner 握手 case：预期观察 160 个 Matrix 命令包与 32 次 A 读，覆盖背压及窗口 lease 失效后接受债务的收尾。这里的数字是测试目标，原始失败运行没有给出完成计数。该 harness 没有 Matrix/HardFloat 数值端点。

原始安全摘要观察到 `CASE_BEGIN`，没有观察到 `SIM_READY`、测试循环 cycle marker 或 case PASS。最后报告的 cycle 是 null，实际时钟数未知，不能写成 0。`SIM_READY` 位于测试 callback 内；测试框架进入 callback 前也可能进行内部 reset/clock 操作。日志只保留有界 head/tail 的标记扫描与安全摘要，因此缺少标记不能证明某个内部阶段绝对没有执行。

“测试 callback 前的启动/准备路径超时”是与当前标记相符的诊断推断；FIRRTL lowering、Treadle 引擎构造、初始化或 pre-body reset 中究竟卡在哪个子阶段仍未知。原始归档没有线程栈，不能把某个 transformation 写成已确认根因。

具体观测边界由已冻结源码确定：`dense_a_hold_interpreter/harness.patch:24–27` 的顺序是 `CASE_BEGIN`、`InterpreterOrigins.emit()`、`test(...).withAnnotations(...)`、callback 内 `SIM_READY`。因此 `CASE_BEGIN` 甚至不能单独证明新的 elaboration 已开始。`run.py:41–62` 仅扫描首尾各 128 KiB 的完整短行；`run.py:236–242` 只有解释命令成功返回后才解析完整 case/class-origin 结果并做 postflight。本次超时走失败分支，未经过该成功收尾。

此外，`dense_a_hold_chisel/AHoldUnit.scala:75` 开始的测试先执行初始化和提交 job 的 `clock.step`，再进入带计数器的循环。即使将来保留了成功的 cycle marker，该数字也只是测试循环周期，不包含初始化、提交及框架可能执行的 reset 周期，不能直接用作全程硬件时钟计数。

## 源码、依赖与资源核对

- 75 个仓库输入 hash 与已发布候选锁定值及当前保存字节一致；重新组合的 15 个 Scala 源文件 hash 与原始 receipt 一致。
- 106 个 Maven dependency 身份与原始独立锁一致；原始 87 项 frontend 锁没有被修改。依赖表身份一致不能代替实际加载类来源检查，也不证明整个 classpath 无版本重叠。
- 原始 receipt 记录 112 个编译输出 class 的 hash；此次只核对其记录形状与计数，没有下载 class 字节进行独立 hash 复算。
- `loaded_class_origins` 没有留在失败摘要；运行后 postflight equality 没有到达。两项均不能宣称已验证。源码/依赖准备阶段的匹配与全程前后无漂移是不同范围的证据。
- 原始 CHIRRTL 资源对象与已通过的 frontend 全端口、reuse=true 配置逐项相等：16 个 A bank（深度 1376）、16 个 B bank（深度 160），均 256 bit、1R1W；Queue3、2048 bit A hold、78 bit 控制增量；有用 operand payload 共 1216 字节。含 Queue memory 共 33 个 memory declaration。
- 这份 inventory 发生在 memory lowering 之前，不是综合面积、真实 SRAM 实现或物理时序结论。解释执行、发射 RTL 仿真、完整 block 数值和有效 MAC 利用率的验收标志均保持 false。

## 计划与清单

源码审计核对了已锁定的八份官方源文本及 Git blob 身份。固定版本 [TesterUtils.scala:37–58](https://github.com/ucb-bar/chiseltest/blob/d764fdf74652426b57c6eae00d71eac19effd224/src/main/scala/chiseltest/internal/TesterUtils.scala#L37) 的创建路径包含新的 elaboration、Low FIRRTL lowering 和 simulator context 创建；[Compiler.scala:21–25](https://github.com/ucb-bar/chiseltest/blob/d764fdf74652426b57c6eae00d71eac19effd224/src/main/scala/chiseltest/simulator/Compiler.scala#L21) 使用 `-E low`；[TreadleSimulator.scala:31–47](https://github.com/ucb-bar/chiseltest/blob/d764fdf74652426b57c6eae00d71eac19effd224/src/main/scala/chiseltest/simulator/TreadleSimulator.scala#L31) 创建 `TreadleTesterPhase`；[PrepareAst.scala:15–36](https://github.com/ucb-bar/chiseltest/blob/d764fdf74652426b57c6eae00d71eac19effd224/src/main/scala/treadle2/stage/phases/PrepareAst.scala#L15) 安排 `LowFormOptimized` 与 `VerilogMemDelays` 等 IR 变换。这些是可能耗时的准备路径，现有证据没有各项实测耗时；单独 JVM 的 CHIRRTL PASS 不能证明测试 JVM 已完成这些阶段。

现有源缓存缺少 ScalaTest callback dispatch、SimController reset、TreadleTester/ExecutionEngine 初始化和 FIRRTL transformation 的完整展开实现。后续最小源码工作是补齐该固定版本调用链，并设计独立的有界进度记录（class-origin 完成、generator 进入/返回、callback 进入）及原 240 秒内的超时前栈摘要。仅提出方案，不修改原始候选、不运行诊断 revision、不自动扩大预算；先继续现有 M16/M128 数值工作。

- [x] 保存第一次失败 run 的四个原始安全成员、ZIP 身份和边界说明。
- [x] 核对源码、组合源码、依赖身份及原始 CHIRRTL 资源。
- [x] 增加失败归档的不可变字节与反例测试，拒绝把未知 cycle 改成 0、虚构 class origins/postflight、抬高预算或把超时改为 PASS。
- [ ] 实际 owner 解释执行握手通过；本次未完成。
- [ ] 后续仅做源码路径诊断，提出可复核的最小观测改进；新执行必须另行获得项目调度批准。本记录不启动第二次 EDA/解释器作业。
- [ ] 完整 M16/M128 数值验收及固定资源有效 MAC 90% 目标继续由原有数值工作推进；本失败归档不替代、不升级其验收结论。

冷校验仅运行 Python 归档测试；不调用 JVM、Scala 编译、解释器、RTL 工具或网络。

验证命令：`python -m pytest -q candidates/qwen2_resident_matrix/dense_a_hold_interpreter_results/test_evidence.py`，及相同命令的 `python -O` 版本；本次各 54 项通过，0.10/0.09 秒。优化模式下生产校验仍使用显式异常，不依赖可被删除的 `assert`。
