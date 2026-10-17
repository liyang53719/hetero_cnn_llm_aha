# Qwen2 packed M128：模型到现有 Chisel 的连接审计

日期：2026-10-17。仅审阅 `liyang53719/hetero_cnn_llm_aha`；未修改 main、staging、冻结运行输入，未运行数值、编译或 EDA。所有文件身份见 `SOURCE_HASHES.json`。

## 结论

现有 Qwen2 prefill 已有多行 Dense、完整 block、因果 Attention 循环和 Host completion fence。应组合现有接口并补控制接线，不需要把它误判为只能 M1、再设计一套 M128 架构。Qwen3.5 H1024 的 M1 Attention-block profile 是另一条路径。

当前 packed M128 是 Python owner/transport 加真实算术后端的数值路径；QK16 Chisel 候选仅完成类编译。两者尚不是完整同一硬件实现。即使当前全模型数值运行成功，也不能直接宣布 RTL、面积、频率或全周期利用率通过。

## 身份与现有能力

以 GitHub connector 核对 main `2e591b6df29fc08504dca264264b149c27e2cf95` 的 blob SHA，与 `hetero_kv_port_20261016` 对应字节一致：Qwen2Block、QwenOwnerProtocol、HostBlockTop、HostBlockCommands、StreamingDense、QK16 owner.patch、raw scratch.patch、QK16 EVIDENCE.json。

下文基础 Scala 路径前缀为 `hetero_kv_port_20261016/chisel/continuous_prefill/src/main/scala/heteronpu/continuous/`：

- `Qwen2Block.scala:13–27`：maxTokens 可到 1024；`:463–490` 已有 token/head/key 因果循环。Dense 亦已有 16 行批次。
- `StreamingDense.scala:230–244,300–322`：按可用 token capacity 分块，rowBase 推进到 job.m；不是 M1 上限。
- `HostBlockCommands.scala:6–15,924,929–935`：原 QK/softmax/PV 三命令融合、实际 M 绑定及返回 tag/status/writeBytes 检查已经存在。
- `HostBlockTop.scala:225` 的 active_tokens_supported=1 属于 Qwen3.5 BF16 Attention-block，不适用于本 Qwen2 路线。
- `attention_qk16_owner_route/owner.patch`：复用 denseWeights[256] 收集 16 个 K 包；8 个 depth step；最终 Matrix FIFO 原槽保持；逐 key 取 16 个选中单元；最后 score 后才允许最终 ACK。

实际已编译应用文件为 `packed_qk16_owner_compile_plan_20261017/scala/chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala`，SHA256 `4375ccf715cf408975c3e45ae595955767b824404ef8337bb260ed807527dc1e`，匹配已发布 EVIDENCE.json。证据只声明 83 sources、474 classes，elaboration/rtl/numerical 均 false。

冻结 M128 `source/` 是组合输入：裸 `attention_packed_owner/schedule.py` 保留早期入口限制；`attention_packed_m128/tiled.patch` 与 `attention_packed_m128_entry/composition.py` 才提供 M128 选择。不可用裸文件的旧限制否定已组合运行路径。

## 已确认数值边界缺口

上述实际编译 QK16 文件：`:329` Scalar 返回原样进入 scalarValue；`:545` 直接缩放 FP32 fold；`:546` 原样写 score 并比较 maximum；`:571` 原样写 PV FP32 累加结果。该文件没有 numericPolicy/materialize。

模型要求：BF16 输入、FP32 8 次深度累加 → 有序 16 项 FP32 fold → 完成 dot 的 BF16 RNE → FP32 scale(0x3db504f3) → score 的 BF16 RNE。score SRAM/scratch 和 maximum 必须消费同一个舍入后值。softmax subtract/exp/按 key sum/reciprocal/normalize 继续 FP32；PV 入阵列时 BF16 RNE，完成输出也要 BF16 RNE。

模型 `ffn_public/prefix_arithmetic.py:77–80`：有限值使用 `(bits + 0x7fff + bit16) & 0xffff0000`，不是截断，结果仍是 32-bit FP32 container。现有 `BlockFloat.scala:12` 的 F32.bf 调用 `Protocol.scala:52–55` 的 TensorMath.bf16Rne，可复用。非有限值策略有区别：模型保留原 bits，Chisel 对 NaN canonicalize；这不能当作所有输入等价。

现有 `official_bf16/chisel_policy.patch:531–532,541` 已有正确 materialize 位置。然而整个补丁 `:18–21` 的 checkShape 要求 maxTokens==1024，而 QK16 guard 要求 <=128；`:41–43` 还要求 resident FFN，`:31` 增加 Dense ABI。因此最小修补应是默认关闭的 **QK 边界片段**，复用既有 F32.bf/边界语义；不能称整个 official policy 已组合。

舍入后 maximum/tie 会改变，继而改变 softmax 差值、exp 输入、分母和输出。仅末端输出舍入不能补偿这个缺口。

## 最小下一补丁与测试

限定 QK16 opt-in：完成 fold 后 materialize；scale 后 materialize；score/max 使用同一值；有限性检查先于 score 发布；保持原默认路径、FMA 顺序、Scalar 接受/返回和 FIFO 债务逻辑。PV 输出及全块其他 official policy 不应被此片段冒充完成。

测试应覆盖：正负 RNE halfway 与 retained LSB 奇偶、signed zero、subnormal、有限值舍入成 infinity；16 项 fold 不提前舍入；两个接近 score 舍入成同值；key 尾组 1/15/16 和跨 16 边界；Scalar/Matrix 背压；score 提交同拍 abort；held result 排空；selected 非有限异常。

rounded dot infinity 可由原 Scalar 输入拒绝，但必须验证原 Matrix 持有债务会排空。rounded score infinity 必须在写 score/max 前拒绝。NaN 不因 canonicalize 而变为合法。

另有独立异常策略差别：模型 `_op` 默认 vector，而 `BlockScalarFloat` legacy Add/Mul 拒绝 inexact underflow。此小补丁不得放宽 legacy acceptance，不得声称全部异常输入等价。冷模型/源检查只能证明其对应契约；授权后还需编译、有限 leaf/controller RTL 测试，再到整块验收。

## 真正 packed M128 的剩余连接

1. **scratch 实际接线**：将 `attention_raw_scratch/scratch.patch` 组合到真实 Dense bank owner；连接 acquire/begin/request/response/ACK/release，绑定 owner/generation/query/KV-head，parentDrained 来自真实 DMA/Matrix/seed/response 债务。当前 QK16 仍写独立 scores SRAM。
2. **六头调度**：移植模型 query→KV组→六头循环、六个 maximum/inverse，保持每头 key 顺序；小寄存器借用必须有整个阶段的排他租约。
3. **384B panel**：实现 96×32bit 物理存储、每 panel 六次串行 raw 读取；key16 边界保持同一个 PV context，只在已接受 step drain 后暂停。模型 list 不是寄存器保留证明。
4. **PV6 供数**：A 提供六个概率，B 提供 128 个 V 分量，其余为零；递增 key，保持最终 result 原槽。V staging 需明确 placement，不可隐含免费。
5. **完成与错误排空**：join scratch/Scalar/memory/Matrix result+done/output-write ACK 债务后再 owner success。复用原 Host fusion/fence；score scratch ACK 不能误当作 DDR 输出已可见。
6. **顶层选择与全块**：HostBlockTop 尚未透传 QK16 开关；增加默认关闭的明确选择及 elaboration 入口，随后验证实际完整 block。还需审查 Dense、RMS、RoPE、SiLU 等 policy 与当前模型的组合，不能由 QK 边界通过推导全部通过。

Scalar 性能优化可后续分片：现有 16 个 vector ALU 没有通用 borrower 端口，SiLU16 也不等于已有任意 Exp/Div 外借。保持串行原 Scalar 可先建立功能连接；不能把尚未接线的并行调度当作已实现吞吐。

## 资源和 MAC 口径

- QK16：复用 denseWeights[256] 1024B、av/acc，候选账本新增 99 control bits；没有新 Matrix 或 tile SRAM。
- scratch：占原 bank 6KiB 地址容量，新增 177 control bits；不是新增 6KiB SRAM。
- panel：目前诚实计 +384B；V/input staging 另行记账，不能把所有模型缓冲合并称为只增 384B。
- M128：QK 55,296 steps/6,912 groups，PV 16,512 steps/256 groups；scratch 27,648 次事务。
- Attention useful MAC 为 25,362,432；全块 useful MAC 为 6,014,828,544，未改变算法工作量。
- DDR gather、Scalar fold/exp/div、bank、held-result 和 FFN SiLU 仍占真实时间。上述计数、CPU wall 或类编译均不能支持 80%/90% 全周期利用率声明。
