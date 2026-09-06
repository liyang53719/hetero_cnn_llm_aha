# 连续 Qwen2 block：已验证范围与运行入口

硬件设计源是 Chisel。所有测试的 SystemVerilog 都由 emitter 生成；原 Revision8B-B RTL 只读取/编译，未修改。

## 本次执行链

同一 DDR arena 内连续运行 15 个阶段：InputNorm、Q/K/V projection+bias、Q/K RoPE、causal GQA、OProj、Residual、PostNorm、Gate/Up、SiLU×Up、Down、Residual。每个阶段最后一笔写回应答完成后才能开始下一阶段。

复用原 `HeteroBF16FmaLane`、`HeteroFP32Alu`、P0 `SharedL2Fabric`、`ElementwiseMemoryEngine`。默认 `--retained` 后端进一步通过 Chisel `RetainedMatrix16Adapter` 接入**未改动的** `qwen2_matrix_command_endpoint` 和 Revision8B-B 16×32、5-context 阵列；整个 dot 的 FP32 partial sums 由原阵列保存。

不是按报告文件串接。C++ 只提供内存事务/延迟/回压和只读参考检查；scratch 初始为 NaN 毒值；读取未写回或未发布的 tensor 会失败。所有 stage 全量输出都比较，不选行、不注入中间 golden。

## 两种后端必须分开

- `retained`：原 512-lane 阵列。当前正确性调度每次只消费 16 个结果，Dense/PV 使用 row0，QK 使用对角结果。其余计算属于无效物理工作。`executedMacs` 来自实际 `step_valid && step_ready` 计数×512；`macs` 是有用工作。**接通阵列不等于高利用率调度完成。**
- `functional`：16 个原 BF16 FMA primitive 的快速功能后端。同一模型控制与内存路径；不能用它的周期声称 512-MAC NPU 性能。

两者使用新的单 beat AXI4 adapter：64-bit byte address、512-bit data、8-bit ID、单请求在途。AW/W 独立握手，只在 B 后返回写完成。平台必须保证该应答对应的数据对本 master 后续读可见。这个 adapter 不是原 pinned-iDMA；也没有声称接通原完整 Command128 graph frontend。

## 精度与资源合同

真实尺寸：hidden=1536、FFN=8960、Q heads=12、KV heads=2、headDim=128；runtime tokens=1–1024。缩小配置只改变几何，使用同一硬件源。

DDR 为 FP32 容器；矩阵权重先转换为 BF16 数值再存入 FP32 容器。Matrix ingress 把激活转 BF16，FP32 FMA 按递增 K 执行；Norm 输出舍入 BF16；RoPE、Residual、统计归约保留 FP32。Attention Q/K/P/V 进入 BF16 MAC；exp(-abs(x)) 使用固定七次多项式，abs(x)>=80 返回0。测试 CPU oracle 独立执行此明确 recipe，不代表已与官方高精度参考或旧冻结 SFU recipe 做了质量签核。

实际非 Matrix 数据 SRAM：row cache 35,840 bytes，元素引擎12,288 bytes，score/prob8,192 bytes，共56,320 bytes，不含流水寄存器和原 Matrix 的 context accumulator。Attention 仅保存单 query/head 的 O(T) 临时量，不在 DDR 写 T×T 分数矩阵。两组 P0 fabric 是独立实例，尚未合并到旧全局1.5MiB owner；物理宏映射未签核。

`QwenBlockLayout` 生成所有 DDR 地址，header 与 JSON 由同一 emitter 输出。readonly 是权重、gamma、bias、RoPE表和初始输入；scratch 为15个实际输出 tensor。不以跨阶段覆盖复用节省空间，先保证生命周期正确。

## 本地 agent：只复核和执行，不改代码

先 `git pull --ff-only origin main`。遇到未确认的工作区修改即停止，不执行 reset/clean。

```bash
# 默认保留阵列：小尺寸完整block + 全部单测 + 错误恢复
bash chisel/continuous_prefill/scripts/run_block_gate.sh work/results/block_retained_tiny_001 tiny 2 retained

# 原阵列、真实尺寸；先2 tokens，之后用新目录跑16、128、1024
bash chisel/continuous_prefill/scripts/run_block_gate.sh work/results/block_retained_real_001 real 2 retained

# 有本地真实权重时，脚本完成layer0导入，不需要写转换代码
bash chisel/continuous_prefill/scripts/run_checkpoint_block.sh \
  work/results/block_retained_real_001 /absolute/model.gguf /absolute/tokens.json \
  work/results/block_checkpoint_001
```

测试依赖：Java17或21、sbt1.10.2、Verilator、C++17、Python3、numpy、pytest。Chisel/HardFloat 版本由工程锁定。默认2个编译进程；运行时间上限可通过 `RUN_TIMEOUT_SECONDS` 设置。长运行很重，严禁改成采样或拿短序列周期外推作为完整性能。

`functional` 可用于更快定位完整 block 功能问题：把最后参数改为 `functional`；这不是阵列验收的替代。

权重 importer 支持 GGUF F32/F16/BF16/Q8_0/Q6_K/Q3_K、safetensors F32/F16/BF16，只预载 readonly。其他格式、模型或尺寸明确拒绝。Importer 的合成文件测试不能冒充本轮已运行真实官方权重。

## 仍未完成，不能转交给不会coding的agent

真实尺寸原512阵列的长序列数值回归需要运行；完整 q1024 block 目前没有通过记录。原 graph Command128/pinned-iDMA系统接入、跨28层程序、原全局SRAM owner、原SFU recipe质量迁移、Qwen3.5 GDN/MoE与Qwen3.8 QSA/PLE/多分支state、工艺SRAM宏绑定及流水收敛仍由主coding端负责。Agent只执行现成入口；失败原样返回，不补代码、不改阈值。

800MHz/1.250ns仍是目标；无DC或STA签核。完整网络、官方权重和性能均独立设门禁。本次不声称三模型q1024完成。
