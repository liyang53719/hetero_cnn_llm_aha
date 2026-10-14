# 现有 Vector16 寄存器借用与 RMS epilogue 局部 RTL

## 范围及计划

- done：生产 ElementwiseMemoryEngine 子类直接复用原 16 个 HeteroFP32Alu、原寄存器和 SRAM；旧类默认不变。
- done：真实 Chisel elaboration、firtool 生成 RTL、Verilator 执行边界/仲裁/异常/复用测试；冻结 M16/M128 真实 postnorm 节点同刺激回放。
- ongoing：本小批发布及精确新 CI 工件闭环。
- todo：将借用接口接到实际 H2048 三 bank owner 和完整 top 仲裁；建立真实搬运/等待时间轴，再预测完整 block 利用率。
- 完整五 block、128 token prefill 全 RTL 数值及 90% 利用率目标仍 open。本批只验 postnorm epilogue，不含 RMS 归约、完整 prefix 或 MoE。

## 资源与实际生产映射

此前“复用现成 16 Scalar”不成立：VectorSilu 中的 16 BlockScalarFloat 未实例化于 bf16GdnCore。本实现选择 Qwen2ContinuousBlock.elem 使用的现有 ElementwiseMemoryEngine，子类没有新增 ALU 或宽数据寄存器。

默认 1.5 MiB 配置的 baseline/loan FIR 逐项库存相等：16 ALU、7 个 512 bit 寄存器、16 个 SRAM 声明；所有原寄存器保留，新增仅 loanState 3 bit 和 loanPoison 1 bit。实际仿真为较小 DDR 配置，完整容量库存另行 elaboration 对比。完整顶层可能还有 legacy vout 等单元，本批库存不能代替全 SoC 资源总账。

RMS 借用三阶段：x×inverse → 1+weight → normalized×gamma。使用原 a/b/value/raw 和控制字段，算术逐阶段 FP32，末 BF16 RNE 由调用端负责。raw 保留 weight，value 保留 normalized，随后 b 覆写 gamma，不添加 normalized 宽缓存。

严格 Add/Mul 默认异常门不变；显式 op6/RMS 的乘法支持有限渐进下溢。仅针对固定 HardFloat MulRecFN RNE：NV 导致 NaN、OF 导致 Inf、乘法无 DZ，所以 finite 输出门可放行 UF/NX 而拒绝非法/溢出。此推理不可推广到其他算子或舍入。gamma Add 仍严格拒 UF；每阶段失败整组清零，不泄漏部分 lane。不提供 exceptionFlags 计数。

## 事务与测试

DDR job 与 loan 同拍由 DDR 优先；DDR request/response 未排空不接受 loan。loan 活动期间不发 DDR；loan poison 的 reset 不能清 DDR poison。held result 保持 tag/status/data；abort/reset 当拍屏蔽原成功 valid，不能同时退休旧成功。外部全局 reset 仍需系统协调 drain。

边界测试覆盖 352 lane 检查、RNE、signed zero、UF 严格拒绝及 IEEE 保留、normalize/weighted 组合下溢、NaN/OF、三阶段失败、未知 op、背压、输入变动、abort/reset、DDR 仲裁/poison；loan 后原 DDR Add/Mul 经真实 SRAM 路径仍成功。

## 真实输入同刺激 RTL

冻结原 M16/M128 postnorm 成功生产者：101 个 Python 源、13 native、13 成功终态、16 个观察记录。准备脚本逐一核验其原始身份；x 仅由实际 residual BF16 位扩展，inverse 和 weighted 取 actual_observed FP32 节点，目标 BF16 取实际 postnorm。参考结果不反馈计算。数据只保留 ignored work，不提交权重或原始激活。

- M16：2,048 次 16-lane loan，32,768 FP32 及 32,768 BF16 输出逐 bit 相同，6,144 Vector primitive issues，10,240 仿真时钟边沿。
- M128：16,384 次 loan，262,144 FP32 及 262,144 BF16 输出逐 bit 相同，49,152 primitive issues，81,920 时钟边沿。

实际时序：E0 接收，E1 normalize，E2 gamma，E3 weighted，E4 最早退休，E5 下次接收，II=5。primitive 最早退休 E2、II=3。以上是 ideal register supply 局部 RTL，含退休空拍；不能当完整 block 周期、Matrix 利用率或系统吞吐。16 lane 在 3/5 周期执行三个规定向量操作，局部计算阶段比例 60%，不是 Matrix MAC 占空比；这些操作不计入 Matrix4096 MAC。

## 复现与证据

先运行 scripts/setup_hetero_chisel_loan_toolchain.sh，再 source work/chisel_toolchain/env.sh。scripts/run_elementwise_register_loan_tests.py 默认运行 2 个 synthetic 测试；显式传入两档冻结 fixture manifest hash 才运行第 3 个真实回放测试。manifest 准备使用 scripts/prepare_rms_epilogue_loan_replay.py，要求真实 summary SHA。

工具：Java21、sbt1.10.2、Scala2.13.16、Chisel6.7.0、Chiseltest6.0.0、firtool1.62.1、Verilator5.032。官方四归档 SHA 固定，HardFloat 20 源与仓库 pin 核对。Maven 原锁交集验证，额外测试依赖仅记录观察 hash，不冒充既有 pin。

原失败记录保留：首次 Verilator PCH 与 Chiseltest forced include 冲突，采用官方 make 选项 VM_PARALLEL_BUILDS=0；随后测试 helper 的 step(0) 拒绝已修复。未修改 vendor/DUT 以绕过数值测试。最终 gate 对全部 135 编译/运行源前后冻结；runner watchdog 限 600 秒并终止进程组。

新 CI 只运行 synthetic 边界和库存局部 RTL，上传 summary/log/生成 RTL 与工具日志；不下载 checkpoint，不上传实际刺激。真实两档回放证据独立保留，不能由 CI synthetic 成功替代。
