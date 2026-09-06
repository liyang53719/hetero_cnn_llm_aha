# 连续 q1024：张量提交、DDR 分区与 SRAM 分块

审查基线：`fdd8f95c9ffe9d49854f796f0daf4ec770d91e27`。
目标是三个指定模型的 batch=1、1024 个输入 token 的文本 prefill，从 token IDs/真实权重到最后 token 的完整词表 logits；不得以抽样算子、文件拼接或计数 trace 代替。多模态输入和 MTP 验证另设门禁，不混入文本 prefill 的完成判定。

## 本次实现，不是整网完成

新增设计源全部为 Chisel；未修改旧生产 `.sv` 或旧 filelist。

- `TensorProgram`：四个 DDR 区域、读写许可、tensor slot/version、请求 epoch、完整写回后提交；拒绝未产生的输入、错版本、越界、活跃 tensor 别名和错误 completion。
- `ElementwiseMemoryEngine`：真实 DDR beat 接口 → SRAM tile → 16-lane FP32 Add/Mul/Copy → DDR 写回。复用原仓库 `gemmini.HeteroFP32Alu` 和 `p0.SharedL2Fabric`。BF16 输入精确展开，输出 RNE，尾部 mask。不是回送 completion 的 stub。
- `ContinuousElementwiseTop`：连接上述模块。支持连续 `Add → Mul → FP32-to-BF16 Copy` 等已实现指令；不是 Qwen decoder。每个消费者从同一 DDR memory service 读取实际生产者写回值，无 start 后 Host 中间态填入。
- `DenseTileCursor`：可变 M/N/K、16×32×128 分块，保留 K 顺序，最后 K 块必须等待写回确认。它只有地址、形状和提交控制，没有新增 Matrix 算术或 DMA adapter，不能单独执行 GEMM。
- `memory_plan.py`：三模型分区规划器；需要真实 device-format 权重清单才能生成地址。尺寸预算是 bring-up 假设，不是已经通过三模型内存仿真的容量下界。

该 top 目前只有 Copy/Add/Mul，未知 opcode 明确失败。Norm/RoPE/Softmax/GDN/MoE/QSA/PLE 不会在该 top 中静默回落 CPU。它们的原仓库组件仍需连接。

## 连续性合同

`MemoryRequest/MemoryResponse` 是内部 512-bit memory-service 合同，不是新的 Command128 格式，不是 AXI。读写地址 64 bit，但当前合法空间限制到已有 descriptor 的 56 bit。只允许一个 outstanding 请求。

写响应必须表示数据已可被后续读观察到，并携带 AXI B/DMA writeback 错误；AW/W 被接受不等于成功。只有全部写响应成功、tag、元素数、字节数一致时，TensorProgram 才发布目标版本，启动后继消费者。返回 stall 时 request 内容保持。

启动前可以配置区域、tensor 和程序以及加载外部输入/权重。启动后配置端口锁定。非 external tensor 每个新 epoch 均失效，external 只能作为不可改写输入。失败后未完成目标不能发布，top 进入 reset-required。复位必须协调 memory bridge 和 pending response，不允许只复位控制器再接收旧应答。

持久 GDN/KV 状态不应简单标成 external 并原地写。后续专用 state owner 必须实现读旧版本、写新版本、提交/回滚和跨请求初始化策略。目前程序槽默认 64、tensor 槽 32，不能直接装入全模型 588 命令；更大参数、层级程序读取和 descriptor 映射是明确后续工作。

## DDR 与 SRAM

DDR 拆为四个不重叠区域：
1. readonly：device-native packed 权重、初始 token、常量和 descriptor；
2. scratch：hidden ping/pong、Norm、Q、Attention O、MLP、路由临时数据；
3. persistent：逐层 KV、GDN 矩阵状态、卷积历史、QSA 索引/summary、PLE 历史；
4. output：最后 token 的完整词表 logits、统计与错误状态。

实际权重 extent 的 bytes/sha256 必须来自量化解包或设备重排后的文件。GGUF 容器长度、参数数×比特率不能替代设备地址占用。CLI 生成器检查清单声明的 SHA 格式；真正文件哈希、模型 revision 和 shape 一致性仍由本地 loader 在下载/打包时验证。地址从 4 GiB 开始以显式测试高地址，DDR-limit 是地址上界而非字节容量。每个 extent 4 KiB 对齐，并保留 4 KiB 哨兵区；哨兵用于验证，不是 IOMMU 页保护。

初始静态布局不做跨 tensor 的 SRAM 或 DDR 别名优化；先保证正确，再引入生命周期复用。预算中的 BF16 KV、FP32 recurrent state、BF16 Gate/Up 临时平面需与批准精度合同交叉确认。KV 的 token/head/layer stride、PLE 全表或流式装入策略、状态矩阵转置方向还未由规划器自动编译。

保留 Shared-L2 容量 1,572,864 bytes（1.5 MiB）。本次 elementwise owner 每个 tile 1024 个元素，A/B/C 各 4096 bytes，只使用 12 KiB；不会将整个 q1024 hidden 常驻片上。三个 buffer 的区间为 `[0,4096)`、`[4096,8192)`、`[8192,12288)`。

CI 通过显式 `--small-fabric` 仅生成这 12 KiB 存储。完整配置生成使用下面的默认命令，不得将缩小实例当作 1.5 MiB SRAM 或 ARM 宏签核。集成进生产系统应共享唯一 fabric；不能把这个自包含测试 top 的 fabric 和已有主 fabric 重复实例化。

## 复跑

从仓库根目录执行（保持新目录，不覆盖旧 checkpoint/artifact）：

```bash
bash chisel/continuous_prefill/scripts/prepare_hardfloat.sh
bash chisel/continuous_prefill/scripts/run_gate.sh evidence_local_new
python3 -m pytest -q chisel/continuous_prefill/tests/test_memory_plan.py
cd chisel/continuous_prefill
sbt -batch 'runMain heteronpu.continuous.EmitContinuous generated_full_new'
```

依赖：Java17、sbt1.10.2、Scala2.13.16、Chisel6.7.0、ChiselTest6.0.0、Verilator、C++17。新工程固定 HardFloat `c1105e6ac6a0dd90fc80893efc4830ab609005d3`；未更改现有 Chipyard。接入前必须确认原 Chipyard 的 HardFloat revision，不能未经比较直接替换已有数值基线。

生成 DDR layout 示例（路径均为本地 agent 提供的真实工件）：

```bash
python3 chisel/continuous_prefill/scripts/memory_plan.py \
  --model qwen35 --weights device_weight_extents.json \
  --ddr-limit 0x4000000000 --out qwen35_q1024_memory_map.json
```

输出文件存在时拒绝覆盖。预算表 `docs/NONWEIGHT_BUDGET.json` 不含真实权重，也不含所有优化/额外 owner 缓冲，不能宣称其为完整硬件最小容量。

## 测试边界

ChiselTest 对真实 TensorProgram/DenseTileCursor DUT 测控制和形状；completion 在这些单测中由测试端驱动，不是数值证明。C++ 数值测试则驱动实际 Chisel 生成电路和 HardFloat ALU，DDR 仅做字节存储/响应，没有算子计算。中间区域预置 0xcc，写入只在 write-response handshake 落地；逐一比较两个 FP32 中间结果和最终 BF16 结果，且检查消费者在 producer commit 后才读。

三个 q1024 hidden 宽度用例分别为 1024×1536、1024×2048、1024×2560 个元素，不代表对应三个模型已跑通。没有真实权重、完整 attention/block、pinned-iDMA、DRAM bank/refresh 模型或 DC。验证结果记录在 `docs/VALIDATION.json`；只有实际通过的项目才能写 PASS。

目标频率仍是 800 MHz/1.250 ns。功能仿真周期不能直接作为频率签核或整网 prefill 性能。已有 BF16 阵列的 512 MAC/cycle 对应 409.6 GMAC/s；本次 16-lane elementwise ALU 不应被加到 Matrix MAC 峰值中。
