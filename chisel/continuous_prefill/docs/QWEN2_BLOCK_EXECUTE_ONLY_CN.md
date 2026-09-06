# 连续 Qwen2 block：本地只复核和执行

## 范围

本增量的硬件源为 Chisel，不允许手改生成 SV。小型连续元素子链、Qwen2 功能 block 与原 canonical 512-MAC NPU 是不同的验收对象。

Qwen2ContinuousBlock 是完整单 decoder block 的功能 bring-up 实现，复用 SharedL2Fabric、ElementwiseMemoryEngine、HeteroFP32Alu 和 BF16 FMA。它具有 16 个 BF16 FMA lane，不是 Revision8B 的 512-lane 阵列。MemoryRequest/Response 尚不是 Command128/pinned-iDMA/AXI 顶层。不能用本路径的 cycles 计算原 NPU 的利用率，不能宣称三模型整网 q1024 已通过。

15 阶段为 InputNorm、Q/Bias、K/Bias、V/Bias、Q RoPE、K RoPE、causal GQA、OProj、Residual、PostNorm、Gate、Up、SiLU×Up、Down、FinalResidual。中间 tensor 由 DUT 写回，memory response 成功握手后才可见；下一阶段读取该实际数据。测试参考只用于比较，不能写入中间 DDR。

真实尺寸配置：hidden=1536，FFN=8960，Q heads=12，KV heads=2，head_dim=128，max_tokens=1024。tiny 配置只用于快速定位；真实尺寸与官方权重是两个独立门槛。

## 本地执行（不要求修改任何代码）

先拉取 main，并保留原来的 checkpoint/build 目录。新输出目录不得已经存在。

```bash
git switch main
git pull --ff-only
bash chisel/continuous_prefill/scripts/run_qwen2_block_verified.sh tiny /absolute/new/path/qwen2_tiny
bash chisel/continuous_prefill/scripts/run_qwen2_block_verified.sh real /absolute/new/path/qwen2_real16 16
```

公开工具要求为 Java17、sbt、Verilator、g++、Python3。HardFloat 由仓库脚本下载并校验锁定版本。缺工具返回77/BLOCKED，不计为PASS。不能让本地 agent 修改工具脚本、Chisel、参考或阈值来绕过失败。

真实尺寸16-token通过后，只改变运行参数执行128和1024：

```bash
bash chisel/continuous_prefill/scripts/run_qwen2_block_verified.sh real /absolute/new/path/qwen2_real128 128
bash chisel/continuous_prefill/scripts/run_qwen2_block_verified.sh real /absolute/new/path/qwen2_real1024 1024
```

这些命令默认使用确定性合成权重。它们不构成官方checkpoint验收。已有匹配当前layout的readonly arena可以作为第四参数；原始GGUF文件不能直接传入。尚未提供并验证的GGUF打包或canonical阵列适配属于后续开发工作，不交给本地agent临时编写。

## 验收

1. 所有子命令退出码为0；Chisel单测不得跳过；生成SV不经手改。
2. 每次block运行STAGE_CHECK必须且只能为phase0到14，每阶段全部元素检查，不是抽样。
3. tiny必须覆盖1/2/17/33token、第二次请求、写响应错误、tag错误与reset恢复。
4. 中间DDR初值为毒值，读未初始化/未发布tensor立即失败；内存模型只处理存取，不执行模型算子。
5. 输出保护区保持不变；末尾byte-enable正确；没有错误后继续发布tensor。
6. source_commit、源码SHA256、工具版本、生成SV哈希、完整日志和RESULT.json必须保存。
7. RESULT的full_network、canonical_512_mac_path、pinned_idma_axi_integrated、dc_timing_pass必须维持false，直到各自独立门禁完成。

遇到失败：保留输出目录与日志，返回命令、commit、首次错误和环境信息；不删工件、不调整阈值、不改代码。本地任务到此停止，由开发侧修复。

## 尚未完成的开发，不是本地执行任务

- 将完整block功能路径映射到原512-MAC阵列、Command128和pinned-iDMA/AXI。
- 与原始数值policy逐项对齐（本功能路径的sqrt/div/exp近似与QK归约顺序需独立审核）。
- 官方GGUF/checkpoint打包器及独立模型数值参考的闭环。
- 28个不同权重layer、FinalNorm和完整最后-token logits。
- Qwen3.5 GDN/MoE及Qwen3.8 QSA/PLE/四路residual的真实连续整网实现。

上述工作不能用元素子链或单block PASS替代。DC只在指定设计源码与数值路径稳定后执行；时钟目标800MHz/1.250ns，但当前没有时序签核声明。
