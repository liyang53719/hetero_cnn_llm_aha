# Host 算子命令驱动 Qwen2 block 内部 owner

## 入口与保留资源

本实现增加 `HostBlockTop`，只暴露 HostCommandLaunch（命令表/descriptor表/权限区域/epoch）、completion/result 和 AXI。没有 BlockLaunch，没有输入 phase 编号，也不先自动执行 block 后再演示 Add。所有操作必须由从DDR读回的合法Command128触发。HostBlockCommands没有按PC自动决定运算的逻辑，opcode、policy和实际tensor形状决定被下发的内部owner job。

共同资源仍为一套原 qwen2_matrix_command_endpoint/Revision8B-B 16x32 Matrix和一套锁定iDMA。命令、descriptor与payload共用SharedMemoryArbiter。算术逻辑从已有Qwen2ContinuousBlock提取为可独立结束的owner模式，legacy模式保留；所有硬件修改在Chisel，保留RTL和生成SV不手改。

## 本次支持的合同，不扩大兼容声明

使用现有公共Python encoder生成原21-op的顺序：RMSNorm、Q GEMM、Q Bias、Q RoPE、K GEMM、K Bias、K RoPE、V GEMM、V Bias、KV_APPEND、QK、Softmax、PV、O GEMM、Residual、PostNorm、Gate GEMM、Up GEMM、SiLU×Up、Down GEMM、Residual。9 Matrix/11 SFU/1 KV。

使用原Command128字段和typed descriptor编码：TENSOR_BASE、SHAPE4、STRIDE3、MATRIX_OP、MATRIX_AUX、SFU_PROGRAM。不新增Host block opcode。这里是重新绑定的FP32容器/矩阵入口BF16-RNE配方，不是此前GGUF量化权重的原始descriptor二进制镜像；仍须单独完成真实checkpoint转换及质量验证。

当前范围为连续、非转置的FP32 tensor；矩阵维度按M/N/K校验；Norm hidden固定为elaboration值；Dense K/N可变并检查上限和16对齐；RoPE使用本profile的head geometry和表格式；SFU_VECTOR为同shape Add或行广播Bias；Activation为SiLU×Up。未支持的dtype/layout/stride/policy明确失败，不能静默fallback。

KV_APPEND将K/V实际输出拷入连续 `[2,T,KV]` cache tensor。它验证冷prefill的完整KV内容与消费者绑定，不是分页KV、旧缓存追加、COW或多请求持久状态验收。

## QK/Softmax/PV三命令流式融合

不把完整score/probability矩阵写DDR。硬件依次读取并校验三条原命令，验证QK transpose-B、M/N/K、GQA几何、Softmax policy、同一逻辑score/probability地址与形状、event连线和PV输出。三条全部合法后，才启动既有有界Attention算术。

score/probability的descriptor表示融合内部逻辑tensor。它们的DDR区域不得被读写；后续普通命令读取这些区域会被拒绝，不能把它们当作已物化的DDR结果。三个成功completion均保守地延迟到PV最终成功写回之后，按QK/Softmax/PV次序发出。这不是三个独立中间矩阵都已写回的声明。

## 连续性与故障

所有初始数据必须位于只读区域；可写scratch只有在本请求中某个producer完整成功写回且completion被接受后才可读。目标采用单赋值，禁止重叠已有输出。KV的两个view允许作为已经完成cache范围的子区间读取。此门禁以整个算子为提交粒度，不是tile级流水和乱序图调度。

owner完成需tag、状态、writeBytes一致。失败不发布成功event、不增加完成数、不启动依赖消费者；保持reset-required。已经成功物理写入但算子后续失败的字节不自动回滚，也不被发布为合法tensor。地址/权限/非法事件在相应payload开始前拒绝。

## 固定执行，执行agent不修改代码

使用新的输出目录，保留旧日志和checkpoint。设置已锁定iDMA依赖（IDMA_EXPORT）；有public离线工具时设置OFFLINE_TOOLS和HARDFLOAT_SOURCE，否则使用Java17/sbt/Verilator/g++。目标时钟800MHz/1.250ns，功能仿真不是DC时序签核。

```bash
bash chisel/continuous_prefill/scripts/run_host_block_unit.sh /absolute/new/owner_unit
bash chisel/continuous_prefill/scripts/run_host_block_gate.sh tiny /absolute/new/owner_tiny16 16
bash chisel/continuous_prefill/scripts/run_host_block_replay.sh /absolute/new/owner_tiny16 /absolute/new/owner_tiny17_moved 17 9467985920 swap
bash chisel/continuous_prefill/scripts/run_host_block_gate.sh real /absolute/new/owner_real16 16
```

real16标准：Host 21 accepted/completed；19实际owner jobs（QK/SM/PV融合）；704,512个实际FP32输出逐字比较，其中包括独立raw投影、独立Bias以及写入KV后的两个cache view；所有logical scores/probabilities保持毒值。与上一版15阶段对应的663,552个输出还应分别比对旧实际输出，不能用新reference替换旧结果。

证据必须包含0退出码、完整21条completion/20份tensor实际与参考文件；本版本准确总数为704,512，不能沿用旧统计。独立verifier按模型形状计算，生成完整CSV。随机回压、opcode/依赖/descriptor破坏和真实iDMA读写故障另有测试；缺工具返回77/BLOCKED，不算通过。

此文档是合同和执行说明，实际PASS以同目录提交的运行证据为准。官方权重、分页KV、588条整网原始图、多层q1024、峰值吞吐及DC仍为独立门禁。
