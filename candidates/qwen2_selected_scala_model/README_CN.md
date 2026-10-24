# Qwen2 selected QK16 / per-head PV 模型模式（可选，TEMP）

## 本次实际改动

新增 `ProductionQk16Schedule`，在一个 Attention `Job(m)` 内执行 token → head → 连续最多16个 key 的 QK 分组 → 原逐 head softmax → 原逐 head / 16列 PV。不是把完整 block 调用128次 M1。保持因果 key 顺序、8个深度步的 FP32 FMA、16条带有序 FP32 fold、completed dot / score / PV output 的 BF16 物化，以及原 Scalar exp7 / reciprocal 路径。

`Qk16LegacyPvClient` 只组合现有 `PackedClient` 和 `LegacyMatrixClient`，共享同一个 MatrixService、resource_address、owner、epoch 和 acquisition；没有第二个 Matrix 后端。QK 结果逐 key 从原持有结果读取，消费完成显式 ACK，结果、done 和客户端回复全部排空后，才进入 legacy PV。legacy PV 仍逐 key 返回/退休结果。失败或缺失退休不允许切换。

默认源文件不改。`selected_hooks.patch` 仅作用于新 overlay；原 packed 六 head 模式、原 owner.patch、M128 profile / admission / source pins 均保持原字节。`selected_owner.patch` 只给新模式在 acquire 前限定1≤M≤128；默认 owner 的1024容量不变。

## 固定来源和对应边界

输入闭包对应 main `1ea9b511fc982b2d928472b0dadd9f794c1c20d8`，tree `e6af2af0b35b7c12907a1ff0b66dd416f0e90571`；19个原始文件及5个选定 Scala postimage 见 `INPUT_PINS.json`。Git对象与独立 c2ae535 提取的对应目录逐 blob / mode 相同，未读旧运行目录。

目标不是 bare main 的 Qwen2Block，而是现有 `production_qk16_rebase` 五文件安装 recipe 的选定 postimage；Qwen2Block SHA256 为 `31b618680b4c750398a0dcf21fa34185dd9fc9b1732e370cfce502915814bd68`。其 `attPackedSelect` → `attNextKey` → `attExpRead` → `attPVStart` 是 QK16、逐 head softmax、legacy PV，不是模型默认的六 head packed PV。因此 bare main 与 postimage 不同本身不是缺架构；本补丁补的是执行模型的调度选项。

仍未证明整个 transport/cache 对应：选定 HostBlockTop 的 cache 为 Dense-only，原 full-model raw-KV Public transport 包装器有独立缓存。也没有证明 Scala Scalar policy、RTL时序或全 block 数值等价。

## 可重复的有限测试

所有命令都只用标准 Python，必传固定源根，禁止隐式旧 fixture。示例：

```
python -I -B candidates/qwen2_selected_scala_model/test_routing.py --source-root RAW_CHECKOUT -v
python -I -B candidates/qwen2_selected_scala_model/test_schedule_numeric.py --source-root RAW_CHECKOUT -v
python -I -B candidates/qwen2_selected_scala_model/test_control_regression.py --source-root RAW_CHECKOUT -v
python -I -B candidates/qwen2_selected_scala_model/test_prepare_geometry.py --source-root RAW_CHECKOUT -v
python -I -B candidates/qwen2_selected_scala_model/run_existing_numeric_regressions.py --source-root RAW_CHECKOUT -v
```

最终总计76项normal /76项 `-O` PASS：26 routing、10新M2数值、8 composition/geometry、1 host histogram，以及16原PackedClient和15原matrix-batch数值回归。初次 `-I` 导入路径失败已修正并保留记录。每个命令亦在 `-O` 下运行；冷进程、1 CPU、20 CPU秒、256MiB限额。control 测试抽取原 client / owner 的实际类定义，服务适配器只提供 synthetic words，executed MAC 计数仍为0。numeric 测试使用现有纯 Python `Fraction` 精确 FMA 与显式 RNE 辅助函数，不是 NumPy / Torch / native / RTL；M2只是一项单元回归，不是M128 prefill。

## 源码安装和真正的全模型入口

```
python -I -B candidates/qwen2_selected_scala_model/prepare.py --source-root RAW_CHECKOUT --output NEW_OWNER_OVERLAY
```

公开交付目录是 `candidates/qwen2_selected_scala_model`，避开现有resident目录的重任务触发范围；运行模块仅由composer放入独立输出的 `candidates/qwen2_resident_matrix/production_qk16_model` 正确命名空间，不直接把公开目录当模型包导入。此命令先检查全部19个固定 raw pins，再使用原 owner.patch 生成原两个 owner postimage；随后应用新的 admission / hooks patch，并复制三个新运行模块。检查精确上下文、零offset / fuzz及固定postimage。只产生6文件 partial owner overlay，不创建完整运行环境、不导入模型、不加载 native、不接受旧 PASS。已有源或输出不符合即拒绝。

实际新 owner 入口为 `production_qk16_model.entry.install(exact_idle_OfficialAttentionOwner)`。这是显式 opt-in，不自动开启历史 full profile。完整 prefill 必须复用现有 `attention_packed_m128_same_host.entry.run` → `dense_block_reduce.check_public_numeric.prepare(rows=128, enable_raw_kv=True, ...)` / `run`，在同一个 full-block命令中产生一个 `Attention Job(m=128)`；本次没有运行该命令。现有全运行 source/hash admission 会正确拒绝本次变化后的闭包，不准改写旧 pins 来绕过它；本候选 `authorize_full_numeric` 明确拒绝。

下一项小工作是为此 exact owner overlay 单独审查和冻结新的 profile/输入闭包，明确选择及验证 raw-KV transport/cache，再接入现有128行 full-block驱动，执行新资格测试。不能继承历史27项PASS，也不能沿用未解释的旧RTL长跑。

## 固定资源和欠填充

`geometry.py` 是源码工作量计划，不是运行测量。物理安装仍为4096 MAC lanes（8×16×32），PV mask1不把分母缩成512。

- QK逻辑形状：1 query × 1..16 keys ×128 depth；每 issue 为16×256×1、mask255，共8个depth步。每步有用16×active_keys，最多256/4096；额外单元仍执行，不能删去。
- PV逻辑形状：1 query ×16输出列 × causal keys；每 issue 为16×32×1、mask1，每步有用16、active capacity512。每个head的8个输出列块分别执行。
- M128源码计划：QK55,296 steps /6,912 groups；PV792,576 steps /12,288 groups；attention有用25,362,432 MAC，已发active capacity632,291,328 MAC。全block有用MAC为6,014,828,544。
- 硬件利用率分母必须是4096×实测全block命令accept至最终completion ACK的周期，包含所有DMA、Scalar、bank等待、控制、停顿与退休；本次无这个测量，不给利用率百分比。Python host ticks、无owner-port handshake次数、issue数量及CPU用时都不能替代周期。

这是刻意保留欠填充的选定Scala对应基线，不是最终90%架构调度；不得为了通过对应测试改回更快的六head方案。

## 现有参考来源（本次未执行）

后续真实参考继续使用既有Qwen/Qwen2-1.5B-Instruct revision `ba1cf1846d7df0a0591d6c00649f57e798519da8` L0、Transformers4.40.1 commit `9fe3f585bb4ea29f209dc705d269fbe292e1128f` 的官方前向路径。M2单元测试没有下载/加载该权重或调用官方前向，不能给这些参考输入新验收结果。

## 验收状态

整体 INCOMPLETE。本次仅新增可执行 owner 调度选项和有限回归。full M128数值、真实profile2/native组合、全transport/cache、Scala/RTL执行及whole-block硬件利用率均未验收。历史 assigned27 PASS独立保留，不向本候选转移；完整29项的显式mask未赋值和softmax_fp32诊断无官方容差问题也不在此伪造解决。
