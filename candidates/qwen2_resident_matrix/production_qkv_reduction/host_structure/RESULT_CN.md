# 原 HostBlockTop 结构门 v5 实际结果

结论：PASS_PRODUCTION_CHIRRTL_STRUCTURE_ONLY。单次运行总耗时 18.499476 秒；编译 emitter 4.673797 秒、CHIRRTL elaboration 12.753569 秒，两个阶段 exit=0，strict cleanup 均完成。没有启动作业或生成新 SV/执行数值。

## 身份与范围

- v5 manifest：74c81f9dfcceff5255c57044887df674117ace10d5919b583f98fa03fcf28eb3。
- 原完整 92 Scala 源闭包；复用已验证 545 production classes，仅编译一个 emitter 源得到 3 个 App classes，原 545 类逐字节保持。87 固定依赖及 JDK 前后核验通过。
- 原 HostBlockTop，official BF16 v2、resident FFN、Public21 QKV reduction 显式打开，burstWrites=true，capacity=maxTokens1024。没有 M128 作业，本次 actual_job_m=null。
- IR 39,580,497 字节，SHA256 e52a110c7c7ca7446b4dad3793a7ce3f6019ebd2ecf221fe0e6220ebd246ad80；672 module + 17 extmodule，共 689 定义，根连通树 689 实例。
- receipt SHA256 c30b2920b58a23f2154e6fbd141b4116d365598d03d6c25a97c407bea97dab42。

## 实际资源和五债务结构

唯一 HostBlockCommands、QwenOwnerKernel、TransposedDenseDownOwner、TransposedDownDenseBanks、ScheduledSiluOwner、VectorSiluOwner、SiluVectorUnit、MatrixPipelineService、LegacyMatrixStreamClient、FfnResidentCoordinator、Public21QkvReductionRouter、SharedMemoryArbiter、RetainedIdmaWeightBurstAdapter、iDMA backend 各一份。

8 个 retained matrix endpoint 黑盒接口及 8 个 tc_clk_gating 黑盒。4096 MAC 是八组 16x32 原端点接口配置依据，黑盒算术实现未执行。SiluVectorUnit 下有 16 个 BlockScalarFloat；整个 top 共 17 个，另一个属于原 scalar 路径，不能漏计为整个 top 仅16。

5 个真实债务寄存器各恰有两条更新：valid AND ready 为1，response/done valid AND ready 为0。接受/退休对分别为 matrix.group/done、dense.burst/burstResponse、dense.writeRequest/writeResponse、io.memory/io.response、matrix.seed.begin/ack。matrixDrained 是 matrixDebt、seedDebt、matrix.result.valid、matrix.done.valid 四者取反的 AND；dmaDrained 是 readDebt、writeDebt、memoryDebt 三者取反的 AND。parser 拒绝重复定义/节点/实例名、额外债务更新及未知布尔形式。这仅证明实际 emitted 结构，尚未证明错拍/故障下的动态退休。

68 个 memory declarations：两组 SharedL2Fabric 各16个 bank（每bank分别16字节×2240、16字节×48）；scores/probs 各1024×32bit；Dense aBanks 16×1376×256bit、bBanks 16×160×256bit；其余两个为队列 memory。上述不含其他寄存器和黑盒内部存储，不能作为完整面积统计。capacity1024 的 scores/probs 合计8192B；若仅比较这两块与128容量，额外7168B。本次没有缩容量。

## 保留的 warning 与下一缺口

5 条 elaboration warning 保存在 emit_chirrtl.log：HostBlockCommands 的 pc 对21项 Vec 索引宽度过大（两处）、attention policy slot 对12项 Vec 索引宽度偏小（两处），TransposedDenseOwner 的 finalValue256项索引宽度偏大（一处）。本轮未修改这些表达式；warning 不能自动推定功能错误或忽略，应结合其上游值域另审。

原 Host 的真实 AXI 错误传播、五债务动态退休和服务切换尚未运行。此前7模块脚本控制 PASS 不能替代这些缺口。本次也没有证明完整29阶段、M128数值或MAC利用率。性能主线仍需 packed QK/PV/scratch/panel 和共享标量/SFU 优化；原 Attention 功能基线不满足90%目标。
