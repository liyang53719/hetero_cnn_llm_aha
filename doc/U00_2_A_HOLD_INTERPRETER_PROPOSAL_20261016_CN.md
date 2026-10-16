# U00.2：实际 A-hold owner 的有界解释执行提案

本文件记录依赖下载之前的路线与预算提案。后续 `candidates/qwen2_resident_matrix/dense_a_hold_interpreter/` 已完成官方新增jar哈希冻结、独立审查与53+53项冷检查，并准备revision1单例入口；尚未启动本候选编译、解释执行或CI。下文“当前调查”是提案形成时的状态，最新可执行依赖身份以该目录的独立 `dependency-lock.json` 为准。已有 frontend run38973350757的四配置结果独立保留。

## 路线与证据边界

建议使用 chiseltest 6.0.0 自带的 `treadle2`，明确选择 `chiseltest.simulator.TreadleBackendAnnotation`。保留实际 `TransposedDenseDownOwner`、32 个 `SyncReadMem` bank 和 Queue，不替换成 Python 状态模型。测试执行的是 Chisel elaboration 后经 FIRRTL 降低的硬件协议；不生成 SystemVerilog，不启动 Verilator/C++，也不执行 Matrix 算术。解释器 wall time 不是硬件周期利用率。

官方 chiseltest tag v6.0.0 已解析为 commit `d764fdf74652426b57c6eae00d71eac19effd224`，Chisel v6.7.0 为 `8db8c1e063c22440c6fcbc61ea7e8923a969ad15`。下列链接固定 commit；八个下载文本均重新计算 Git blob SHA-1 并与 GitHub 返回身份一致。

- [TesterUtils.scala:43–51、61–68](https://github.com/ucb-bar/chiseltest/blob/d764fdf74652426b57c6eae00d71eac19effd224/src/main/scala/chiseltest/internal/TesterUtils.scala#L43)：elaborate → low FIRRTL → 所选 simulator；未指定 backend 时也默认 Treadle。
- [Compiler.scala:21–25](https://github.com/ucb-bar/chiseltest/blob/d764fdf74652426b57c6eae00d71eac19effd224/src/main/scala/chiseltest/simulator/Compiler.scala#L21)：调用 Scala firrtl2 的 `-E low`。独立的 SystemVerilog 方法不在本路径上。
- [TreadleSimulator.scala:12–14、31–47](https://github.com/ucb-bar/chiseltest/blob/d764fdf74652426b57c6eae00d71eac19effd224/src/main/scala/chiseltest/simulator/TreadleSimulator.scala#L12)：构造 JVM 内的 `TreadleTesterPhase`。
- [ChiselBridge.scala:272–273](https://github.com/ucb-bar/chiseltest/blob/d764fdf74652426b57c6eae00d71eac19effd224/src/main/scala/chiseltest/simulator/ChiselBridge.scala#L272)：保留 memory 的 sequential/read-under-write 属性。
- [PrepareAst.scala:15–23](https://github.com/ucb-bar/chiseltest/blob/d764fdf74652426b57c6eae00d71eac19effd224/src/main/scala/treadle2/stage/phases/PrepareAst.scala#L15)：采用 LowFormOptimized 和 VerilogMemDelays；后者是 memory-delay IR transform，并不代表输出 Verilog。
- [SyncReadMemTest.scala:17、26–39](https://github.com/ucb-bar/chiseltest/blob/d764fdf74652426b57c6eae00d71eac19effd224/src/test/scala/chiseltest/iotesters/examples/SyncReadMemTest.scala#L17) 与 [QueueTest.scala:14–44](https://github.com/ucb-bar/chiseltest/blob/d764fdf74652426b57c6eae00d71eac19effd224/src/test/scala/chiseltest/tests/QueueTest.scala#L14)：官方测试覆盖逐沿同步 RAM 写/读及 Queue 握手/保持。
- [Chisel versioning:13](https://github.com/chipsalliance/chisel/blob/8db8c1e063c22440c6fcbc61ea7e8923a969ad15/docs/src/appendix/versioning.md#L13) 规定同一 major 的 minor 二进制兼容；[chiseltest 6.0.0 release](https://github.com/ucb-bar/chiseltest/releases/tag/v6.0.0) 声明兼容 Chisel 6，但不支持较新 probes/layers。这里的 AHoldProbe 只是普通 IO Bundle，不使用 Chisel Probe API。

降低会拆分 aggregate Queue memory，并引入同步读延迟寄存器。资源声明仍以原始 CHIRRTL 检查，不可强制解释器内部 IR 仍恰好只有 33 个 memory 声明，也不可据此声称综合面积相同。

## 首次只执行一个已有用例

源为 `candidates/qwen2_resident_matrix/dense_a_hold_chisel/AHoldUnit.scala`，SHA-256 `3228044e24fbc8151071e60f9f4fd4cd35d3f14412c507f3356787b4cd83431a`。第 11–26 行观察实际 owner；75–159 行驱动真实接口；161–164 行的 reuse=true 用例为 M16/K32/N160，检查全部 160 个 packet。

用直接 ScalaTest Runner 选择 `-s heteronpu.continuous.AHoldUnit -z reuse=true`，不经过 sbt。保留初始 25-cycle 背压、周期背压、私人 A payload 稳定性、Queue3 加 pending-response 信用、context0 同沿返回到 context1 B-only issue，以及结束时 lease invalidation、全部已接收 DMA 债务退休与锁定状态。测试上限仍为 20,000 cycle，成功 packet 数为 160、A gather 为 32。它不覆盖 reuse=false，也不覆盖 K256 的同沿坏 DMA 用例；这两项等待首例实际开销后另行批准。

冻结源不修改。未来 runner 只对私有复制的测试 harness 施加可审查的零模糊 patch：显式 Treadle annotation、case_begin / sim_ready / 有界 cycle / case_pass 标记，以及最终计数。必须精确匹配一个通过的 ScalaTest 用例，不接受零测试、取消、失败或仅 elaboration 成功。额外 emitter 检查带观察端口的 AHoldProbe 原始 CHIRRTL；只允许顶层名称/观察端口差异，bank/Queue/hold 声明维持已审核值。

## 依赖增量必须显式冻结

保留 Scala/compiler/plugin 2.13.16/6.7.0、Chisel 6.7.0、ScalaTest 3.2.19。不引入旧版 standalone Treadle/FIRRTL，也不降低 owner 的 Chisel 版本。官方 Maven POM 的直接及传递依赖调查得到：现有 87 jars 减去 6 个旧版本，加上 25 个新坐标，候选 classpath 为 106 jars。

新增包组包括 chiseltest 与 firrtl2 6.0.0、ANTLR4 runtime 4.9.3、ScalaTest/Scalactic 3.2.19。替换 JNA 5.13.0 → 5.14.0，以及 json4s 的 ast/core/native-core/native/scalap 五个 jar 4.0.6 → 4.1.0-M4。后者是 firrtl2 POM 的实际要求，不能只追加 chiseltest 两个 jar 并沿用既有 87 项声明。既有 os-lib0.9.2、scala-xml2.2.0 和 Scala2.13.16 覆盖较旧传递要求。

当前调查只读取官方 POM；尚未下载新增 jar，因此这是坐标与 POM 身份提案，不是已冻结的可执行 jar lock。执行前需逐个获取官方 Maven 原件、锁定 SHA-256，核对上述六项替换没有旧/新版本同时出现，编译前和结束前重新核验全部 jar 与源码。既有未使用的 frontend 依赖可保留；库存在不代表允许启动其外部工具。

## 待审核的硬预算与停止条件

首次单例总计 600 s：依赖 120 s、编译 180 s、结构审计 30 s、单例 fresh elaboration/降低/解释执行 240 s、清理与证据 30 s。仅一个 JVM、`-Xmx2048m -Xss4m -XX:ActiveProcessorCount=1`；CI 外层 12 min。没有 waveform、自动重试或并行 EDA。超时需终止整个进程组并保留失败小证据，先查原始失败再决定下一步。

这是资源和时间上限，不是完成预测。已知 frontend 只证明编译约 15.713 s、四份 elaboration 约 4.776 s；没有测过约 11 MiB owner 的 firrtl2 降低、解释器初始化、峰值 heap 或逐 cycle 开销。若 2 GiB/240 s 不足，不能悄悄扩大预算。

只上传小型 stage/result/hash/资源摘要和脱敏诊断，不上传 FIRRTL、jar、class、波形或完整日志。未来 PASS 必须同时声明 interpreted_hardware_protocol=true、emitted_rtl_simulation=false、matrix_arithmetic=false、full_business_block_acceptance=false、hardware_timing_or_utilization=false。
