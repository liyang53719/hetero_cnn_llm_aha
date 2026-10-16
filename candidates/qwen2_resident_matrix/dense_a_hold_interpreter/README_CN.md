# 实际 A-hold owner 的单例 Treadle 资格检查

本候选准备了真实 owner/banks/Queue 的解释执行入口。独立审查与53+53项冷检查已通过；workflow revision1 准备为只由自身YAML变更触发的 attempt1 单次发布，尚未运行本候选的 Scala 编译、Treadle、RTL 或 CI。最终发布由父任务预算 gate 控制；不自动重试。新的YAML发布或手动dispatch仍会创建新的attempt1，不能把run_attempt条件理解为永远只允许一次。既有 frontend 原始四配置证据、A-hold 冷模型与 native 算术证据均未修改。

`prepare.py` 复用已冻结的 `dense_a_hold_chisel.prepare` 生成 13 个实际源单元；原始 `AHoldUnit.scala` 私有复制后只加入显式 Treadle backend 与固定状态/计数标记，再增加 `ProbeElaborate.scala`，共 15 个编译输入。原有 owner、bank 和每个 packet 的运算/握手检查保持字节一致；无替代 bank 模型和 peekMemory 写入。

只选择 M16/K32/N160 的 reuse=true 用例：160 个 Matrix command packet、32 次 A gather，初始25-cycle及周期背压、Queue3与 pending-response 信用、私人 A 副本保持、context0→context1 同沿 bypass、lease invalidation 后全部已接收 DMA 债务退休与锁定。用例的外部 Matrix/DDR 为合成协议响应，Matrix 算术不实例化。reuse=false 和 K256 同沿坏 DMA 用例本次不执行。成功只表示这个解释执行协议用例通过。

## 固定依赖与主源证明

源机制及官方 commit 固定链接见 `doc/U00_2_A_HOLD_INTERPRETER_PROPOSAL_20261016_CN.md` 和 `dense_a_hold_interpreter_plan/upstream-source-identities.json`。chiseltest6.0.0 内置 treadle2：ChiselBridge→Scala firrtl2 LowForm→VerilogMemDelays→JVM 执行；不需要 firtool、SystemVerilog、Verilator 或 C++。普通 SyncReadMem 时序通过降低后的延迟状态保留。原始 CHIRRTL 资源审计独立于内存拆分后的内部解释器表示。

`dependency-lock.json` 是本候选单独的106-jar classpath：保留既有87项中的81项，替换 JNA 与五个 json4s，增加25个带 SHA-256 的官方 Maven 原件。25个新 jar 共19,329,566B，各自也匹配官方 `.sha1`；哈希阶段未执行 jar。原87项 lock 不修改。编译器 Scala2.13.16、Chisel/plugin6.7.0 保持；chiseltest/firrtl2 为6.0.0，ScalaTest/Scalactic3.2.19，JNA5.14.0，json4s4.1.0-M4，ANTLR runtime4.9.3。

原 frontend classpath 已含 Jansi1.18/2.4.1 和 JLine aggregate3.27.1/模块3.24.1 的重叠；这些旧组件未被本改动新增。直接非交互 ScalaTest Runner 明确指定 `-oW`，不使用这些 console/Resolver 工具。这里固定的是明确的 classpath，不声称所有保留工具的各条未使用路径已执行验证。后续实际单例仍可能暴露链接、降低或解释器兼容问题，失败必须保留。

## 预算与证据

总600s：依赖120s、编译180s、结构30s、解释执行240s、保留30s清理。一个JVM，heap2GiB、stack4MiB、ActiveProcessorCount1；这是JVM配置上限，native开销和实际峰值RSS尚未测量。用例保持20,000-cycle上限；无waveform、自动重试或并发EDA。每个阶段进程组超时后整体终止；解释器准备成本计入240s。

先对原 owner 与仅加观察IO的 AHoldProbe 分别生成原始 CHIRRTL，要求32个原bank/1R1W、Queue3、2048-bit hold以及全部寄存器形状一致。之后执行一个指定的 ScalaTest；须看到case_begin、sim_ready、完整有序cycle标记、最终160/32/debt计数及恰好一个ScalaTest通过。

编译成功后记录完整class文件集合及逐文件hash，并在结构/解释执行前后拒绝class增删改。编译前、解释执行前、返回PASS前重新核验仓库输入、15个私有源、workflow、pins、106个jar与Java executable；记录实际Java21版本。实际ScalaTest进程还输出Treadle、FIRRTL、Chisel、json4s、JNA、ScalaTest、Scala七个class的CodeSource，必须逐项指向选定jar，记录坐标与hash。JVM子进程使用空PATH并去除可覆盖JVM参数的环境变量，禁止意外找到外部EDA/compiler工具。输出目录若出现Verilog、native object/library或waveform也拒绝PASS。

失败summary保留case_begin、sim_ready和最后一个合法cycle标记；本候选专用诊断选择器保留直接scalac/ScalaTest/OOM错误并脱敏，不改动原SBT helper。只上传summary、source-sha256（含class清单）、dependency-sha256和至多4KiB诊断；完整FIRRTL、class、jar和日志留在临时目录。成功标志为 `PASS_ONE_CASE_INTERPRETED_PROTOCOL`，必须同时保留 emitted_rtl_simulation=false、matrix_arithmetic=false、full_business_block_acceptance=false、hardware_timing_or_utilization=false。

冷检查命令（不运行Java/网络/EDA）：

```
python -m pytest -q candidates/qwen2_resident_matrix/dense_a_hold_interpreter/test_runner.py
python -O -m pytest -q candidates/qwen2_resident_matrix/dense_a_hold_interpreter/test_runner.py
```
