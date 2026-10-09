# Host Q/gate、K、QK Norm 与 partial64 RoPE：下一有界闭包

状态：2026-10-08设计审查快照，2026-10-09追加执行进度。下文历史行号、源码SHA及接口建议保留原样，不代表最新源码逐行状态。
Host V四组M128及legacy回归CI已分别收尾，见 `doc/U00_2_HOST_BF16_V_20261008_CN.md`。生产Host Q/gate、K、V已有cold0/carried127两个M1实际投影与alias拒绝局部结果，见 `doc/U00_2_HOST_QKV_PROJECTION_20261009_CN.md`；全M128、新提交fresh CI、余下故障/reset及Norm/RoPE仍未完成。候选SharedL2与生产Host分别验收。
优先级：GDN真实生产Host和状态续算与attention-path后续并行推进，不把完整Attention或候选full128当作GDN启动前置；单元实验不能升级为main完整GDN验收。

## 结论：最短的下一条可验收链

沿用同一个 HostBlockTop → HostBlockCommands → QwenOwnerKernel，使用 7 条显式 Command128：

1. Dense Q/gate：A[M,1024] × B[1024,4096] → packedQ[M,4096]
2. Dense K：A[M,1024] × B[1024,512] → packedK[M,512]
3. Dense V：现有已接通的 native BF16 V 路径
4. QK Norm(Q)：packedQ[M,4096] + q_norm.weight[1,256] → normQ[M,2048]
5. QK Norm(K)：packedK[M,512] + k_norm.weight[1,256] → normK[M,512]
6. partial64 RoPE(Q)：normQ[M,2048] + trig[M,64] → ropeQ[M,2048]
7. partial64 RoPE(K)：normK[M,512] + trig[M,64] → ropeK[M,512]

每条命令仍只有一个连续 DDR 输出区间，继续使用现有完成事件与 publication 规则。Q gate 保留在 packedQ 已发布张量中，按每头 [Q256, gate256] 交错布局保持原始 BF16 位；此闭包不增加独立 gate 输出、不覆盖 packedQ，也不先做多输出融合。

这样不必改 Host 的单 dst publication，不必修改 StreamingDenseOwner 的 Matrix 调度/写回，不必建立另一份 Matrix 或 detached top。暂时付出的代价是 Norm/RoPE 各一次 DDR 中间态读写；先证明生产入口闭包，再评估融合。

## 1. 当前实际入口与可直接复用模块

以下路径均相对仓库根。

- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/HostBlockCommands.scala:182-244`
  - nativeV 已检查普通 opcode=0x20、engine=2、flags=0，BF16 A/B/D，M<=128，完整 tensor prefix、token window、policy version=2、role=2。
  - `activeA=A+tokenBase*2048`，当前 V 的 `activeD=D+tokenBase*1024`；bind 为 `m=count,n=512,k=1024`，三个 BF16 storage flags=true。
  - `sourceLive`、`freshSpan`、exact owner tag/status/writeBytes 检查和 `:261-268` publication 已可复用。只发布实际 ACK 且 Host completion 已被接受的 active D；不能发布未写前后缀。
- `.../StreamingDense.scala:20-35,81-110,175-244,301-329`
  - `StreamingDenseOwner` 已支持一般 n、native BF16 A/B、最终 RNE BF16 D、旧 FP32 路径、m 分批、五 context、DDR burst 与有界双缓冲。
  - n=4096 的 flat packed Q/gate 以及 n=512 的 K 不需要另一个 Matrix feeder。当前 `s.maxRow=4096`、k=1024 已落在资源边界内。
  - 保留 `kind==Dense`、范围/alias、全 active output finite 检查，写 ACK 后累计 `bytes`，最后 Matrix done 与所有 store drain 后才 done。
- `.../MatrixPipeline.scala:32-64` 及同文件其余实现
  - 现有唯一 `MatrixPipelineService` 提供 `MatrixStreamPort`；八个 `RetainedMatrixEndpoint` 是同一逻辑 4096-MAC Matrix 的物理 slices。
  - `MatrixStreamGroup={opcode,sliceMask,tag}`；step 包含 BF16 a[16],b[256], context,clear,last,finish,emit；result 为 FP32 value[16][256]。
  - 本闭包不改其算术、context、clear/last、结果 FIFO、abort 或 clock gating。
- `.../QwenOwnerProtocol.scala:49-100`
  - 现在 mode 为 2 bit：0=旧 core，1=Dense，2=SiLU，3 空闲。
  - 可把新 QK SFU owner 接到 mode=3，扩展内部 memory/result mux；外部 Host job/done 仍是一笔事务。
- `.../HostBlockTop.scala:33-75`、`.../SharedMemoryArbiter.scala:7-80`
  - 外层 hub 仍是两个 client：metadata reader 与 owner。新 SFU 是 owner 内部的第四种 mode，外层不增加 client、iDMA 或 AXI master。
  - 新 SFU 首版使用普通 512-bit `MemoryRequest/Response`，已有 dense burst/read/write 直连保持不变。

## 2. 第一小步：Q/gate、K 的实际 Dense 入口（M1已局部验真）

修改范围建议：HostBlockCommands、HostBlockTop 的显式 feature/profile 选择、QwenBlockShape 的新 profile 工厂、Host descriptor serializer/contract/fixture 与测试。StreamingDense、MatrixPipelineService 的计算实现无需改动。

- 不把现有 `bf16V` 静默变为全 QKV。增加默认 false 的独立 `bf16Qkv` / 明确 profile，保留现有 EmitHostBf16V 与 version-2 V 字节编码、默认 Qwen2 emit 行为。
- 使用 owner-managed version=2 projection policy，按明确 feature 允许 role=0(Q)、1(K)、2(V)，norm_policy=0，tensor/tile16=1，九个 address records 仍全部为零 sentinel。
- `N = role==Q ? 4096 : 512`，要求三张量都是 contiguous BF16 rank2，A[M,1024]、B[1024,N]、D[M,N]，MatrixOp 精确 m=M,n=N,k=1024，其余位为零，MatrixAux 保持 native BF16 的既有 payload。
- 将当前 V 硬编码的 activeD/end、bound.n 和 writeBytes 参数化：`D + tokenBase*N*2`、`count*N*2`；A 仍 `A+tokenBase*2048`。
- 保持完整 allocation/permission 检查与所有 prefix/policy 索引不重复；active A 必须只读或当前 launch 实际已发布，full B 必须 live；输出 active D 必须 fresh、不得与完整 A/B alias。
- Q/gate 权重仍是完整 1024×4096 row-major；只做官方 weight 转置/排布搬运，不预计算投影、不把 native projection 写进 DUT 输入。
- packed Q 是八个连续 head，每个 [Q256,gate256]，不能误用全 Q2048 后接全 gate2048 布局。

该步骤已完成的本地边界是baseline cold0/carried127各M1的Q/gate/K/V实际数值，以及cold0输出alias在owner前拒绝。来源为403个dirty-build源hash绑定，不能称精确新提交CI；count16/full128及余下故障仍待验，不等于QK postprocess完成。

## 3. 3-bit kind 已满：必须显式内部版本扩展

现状：`QwenOwnerProtocol.scala:7-14` 的 kind 为 UInt(3.W)，0..7 已全部分配；写入整数 8 会截断成旧 Norm=0，不能使用。

建议明确方案（内部协议，不是新 Host opcode）：

- `QwenOwnerJob.abiVersion: UInt(2.W)`；旧 job 版本为 0。
- `kind` 扩为 UInt(4.W)，旧 0..7 数值保留；新增 8=QKNorm256、9=PartialRoPE64，仅 abiVersion=1 可执行。
- 增加一组有界扩展字段：`role:UInt(2.W)`、`tokenBase:UInt(32.W)`、`headDim:UInt(16.W)`、`rotaryDim:UInt(16.W)`、`policy:UInt(8.W)`、`epsilon:UInt(32.W)`。旧 job 必须把这些字段设为零。
- 复用旧地址字段：a=已偏移到 active window 的输入，b=gamma 或 active trig table，dst=active 输出；c=0。m=count；n=输出列数 2048/512；k=输入列数（Q Norm 4096、K Norm 512，RoPE 为 n）。保留 tag={epoch,pc}、writeBytes、三个 storage flags 的显式值。
- 路由必须同时检查完整 `(abiVersion,kind)`：只有 `(0,1)` 进 Dense、`(0,6)` 进现有 SiLU，旧 0..7 只在版本0进入旧 core；只有 `(1,8)`/`(1,9)` 进 QK SFU mode=3。未知版本、未知 kind、高位非法或新字段污染旧 job 必须在 memory/Matrix issue 前返回 Unsupported。
- 所有 producer、consumer、direct-owner test harness 和 C++ 端口绑定一起更新；禁止 `.kind(2,0)`、未经检查的 `asUInt` 窄化、按旧总宽度切片。
- 内部 result 格式可以不扩：tag/status/writeBytes/cycles/usefulMacs/executedMacs 足够；新 SFU 的 Matrix MAC 计数为零。数值 flags 可以先作为明确 debug 输出，不能悄悄吞掉 fatal arithmetic status。

QwenOwnerKernel 的 mode 仍可保持 2 bit，mode=3 接新 owner。未识别的 job 应使用显式 reject 状态/结果，而不是落入当前默认的旧 core 分支。

## 4. Host SFU 描述符：保持 public opcode 与一个 dst

新增独立的 version-3 QK SFU contract（提案，尚未实现），不要复用候选 version-1 的本地 L2 地址语义，也不要把 version-2 V 零地址字段重新解释为可写私有 SRAM 地址。

- QK Norm 仍 opcode=0x32, engine=3, flags=0；RoPE 仍 opcode=0x34, engine=3, flags=0。
- 每条 A/B/D 都使用现有 tensor_base→shape4→stride3，BF16 dtype5、global0、rowmajor0；rank2 的 dims=(M,N,1,1)、ELEMENT strides=(N,1,1)。
- A stride tail：现有 SFU_PROGRAM(type0x20) → QKV_POLICY(type0x1a, payload version=3) → NULL。B/D tail 为 NULL。这样不需要第四个 root或 raw额外地址。
- SFU_PROGRAM: program_id 对应原 opcode；input_count=2，output_count=1，input_dtype=5，output_dtype=5，lane_width_bits=16，vector_lanes/program_flags/reserved=0。
- version-3 policy 保留 role、token_base/count、tensor/tile16；Norm 的 policy byte=0xc1，RoPE=0xb1。headDim=256、rotaryDim=64、epsilon=0x358637bd 由明确 version/opcode 固定合同决定，Host bind 时写入内部字段并由 owner 再核验。V role2 在这两种 SFU 命令中拒绝。
- 修改 `HostBlockCommands.scala:157-180` policy walker：当前仅 MatrixAux 非NULL 才继续扩展，普通 SFU 第一条读完就 validate；需要为明确 feature/opcode 的 SFU_PROGRAM 非NULL tail 读取下一条 version-3 policy，并严格固定长度、NULL终点、common/reserved和所有跨root/policy循环。
- 不放宽当前 `sfuPolicy()` 的旧 FP32 检查；添加 separate typed predicate，保持旧 SFU 规则原样。

形状与窗口：

- Norm Q: A[M,4096], B[1,256], D[M,2048]；Norm K: A[M,512], B[1,256], D[M,512]。
- RoPE Q/K: A、D[M,2048或512]；B[M,64]，每行 cos[0:32] 后接 sin[0:32]，BF16，共128字节。
- token window 与 Dense 相同，只绑定并发布 active 行；所有 source/destination allocation 仍检查完整范围。
- 对 gamma、trig 走 typed tensor reader 的只读/permission、alias 与 live 检查。首版将它们限制在 launch 的只读 region 内，避免未经完成确认的常量生产者或跨命令缓存污染。
- trig 行必须是与该次实际 cold/carried 输入位置相对应的显式系数。tensor行号 token_base 不应被偷换为从零重新计算的位置；采用每次 launch 的位置匹配表，不新增在线 sin/cos 生成，也不对 carried 假装 position=0。

## 5. 新有界 QK SFU owner：复用算术叶子，不复用 detached candidate top

建议在 `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/` 新增一个 QK SFU owner 和对应 retained SFU BlackBox 包装。它是现有 QwenOwnerKernel 的 mode=3，不具有自己的 Host launch、Matrix 或 iDMA。

可直接复用的 RTL：

- `rtl/sfu/qk_norm256_bf16_candidate.sv:30-54`
  - ready/valid 输入：packed_i[8191:0]、weight_i[4095:0]、role_i、head_dim_i、policy_i、epsilon_i、tag_i。
  - ready/valid 输出：norm_o[4095:0]、gate_o[4095:0]、status/tag/flags，以及可选 mean_eps/inv trace。
  - 内部既有 `fp32_rmsnorm256_chunked(QK_CANDIDATE=1)`、reduce16、rsqrt_nr、RNE BF16 converter 原样复用。
- `rtl/sfu/fp32_rope_pair_bf16_pipe_candidate.sv:6-22`
  - 每对输入 even/odd/cos/sin 为精确 BF16→FP32 widen，输出 BF16 even/odd，独立 ready/valid、flags。
  - 每个乘积先 BF16 RNE，再做加/减并末端 BF16 RNE；不得替换成旧 FP32 RoPE 或重新结合计算。
- `rtl/integration/rope_bf16_l2_candidate.sv:105-138` 可直接作为已验证的映射/控制参考：每头32对 `(i,i+32)`，只旋转前64元素，tail[64:256]原位逐位复制。
  - 这个模块自己的 L2 请求/写入协议不等于 Host DDR acknowledged MemoryRequest；首版建议复用其 pair 叶子与映射，而不把整个 SharedL2 owner 跨接为新 top。

建议 owner 状态（可以合并，但完成条件不可省）：

`idle → validate → loadConstantReq/Wait → loadHeadReq/Wait → normIssue/Wait OR ropePairIssue/Wait → storeReq/Wait → nextHead → nextToken → finish/locked`。

- 一次只缓存一头 packedQ=1024B 或 K=512B、gamma=512B、当前 token trig=128B、Norm/输出头512B；不缓存全128行、不增加 Matrix。
- gamma 每个 Norm job 从 DDR 读取8个64B beat并校验成功后复用所有heads/tokens；该 job 完成/错误/reset 即失效。存入的是官方 q_norm/k_norm 原始权重；叶子执行 `gamma=RN32(1+weight)`，不得在主机预加1后再重复加。
- Norm Q 逐头读取 [Q256,gate256]，仅写 norm256；gate 已在 packedQ 中存在，不转换、不覆盖、不另行声明 gate output 发布。
- RoPE 每 token 先读2个 trig beat，对该token的8个Q heads或2个K heads复用；每头仅32 pair握手，tail原始BF16复制。
- 普通 memory 请求固定64B，mask=全64 byte；tag=Cat(job.tag,sequence)。必须校验 response tag/error，最后实际write ACK后才累计 writeBytes，所有头/行完成后才 done；错误锁定并要求reset，不发布部分结果，不声称可回滚已经写入DDR的字节。
- `QwenOwnerProtocol.scala:75-83` memory/responses 的 Seq 从3个扩到4个。SFU不需要 burst首版端口；保留 Dense 的 burst/write通道直连。
- 当前 Matrix mux 以 `!useDense` 选择 legacy；在新 SFU mode 下保证 core/legacy 无job或在途请求，明确禁止新的Matrix issue。不要因为新mode而添加另一套Matrix。

## 6. 旧 Qwen2 与算术风险必须明确保护

不能仅取消 qwen35VOnly guard 后复用旧 Norm/RoPE：

- `Qwen2Block.scala:263-277` 的 Norm 归约范围与 mean 固定 `s.hidden`，FP32 DDR container，旧直接 gamma 乘法。Qwen3.5 QK Norm 是每head256，`1+weight`，不同归约/rsqrt与BF16节点。旧路径不适用。
- `Qwen2Block.scala:399-410` 的 RoPE 分半距离是 `headDim/2`，遍历整headDim，FP32 container；Qwen3.5 partial64 是距离32、只前64、尾192 raw copy。
- `Qwen2Block.scala:242` 目前拒绝所有 qwen35VOnly owner jobs及native A/D flags；这个保护应留在旧 core，QK新SFU绕行到mode3，不能放宽旧 core几何。
- `Qwen2Block.scala:13-26` 的显式 profile 目前保证 H1024、Q2048、packedQ4096、F3584、heads8、kvHeads2、headDim256；新增独立 QKV profile时，旧 default q==hidden、packedQ==hidden、旧1536/128规则保持不动。不要把旧 V-only profile静默升级。
- Norm叶子只支持 zero 或 BF16指数95..158，非有限/超域必须在该头写出前返回错误；inexact可报告，不能吞掉invalid/div0/overflow/underflow。不能把候选通过样本外推为任意BF16支持。
- 权重/输入与输出的BF16舍入路径已在StreamingDense固定；不能因新Norm/RoPE而更改Matrix的每K累加顺序。

## 7. 源码/构建与验收顺序

新增 SFU BlackBox 必须跟生产 Host 在同一构建/身份清单里：

- `integration/gemmini/EmitHeteroFP32Pipelines.scala` 提供 `HeteroFP32MulPipeTag12` / `HeteroFP32AddPipeTag12`；当前生产 `production_source_identity.py` 的编译源只显式包含 BF16Fma 与 FP32Alu，需要纳入该文件。
- 在同一个 HostBlockCollection 的 primitives emission 加入所需根，保持单次 HardFloat 联合 elaboration，避免把另一份完整 primitives SV 拼接导致重复module名。参考 `chisel/matrix_norm_rope_hardware/src/main/scala/EmitMatrixNormRoPEHardwarePrimitives.scala`。
- 生产 manifest/source hashing 目前遍历 rtl/matrix 和 rtl/integration，不包含 rtl/sfu；必须显式纳入Norm/RoPE叶子、converter、reduce、rsqrt以及 `rtl/sfu/fp32_rsqrt_coeffs.svh`。不能让新 SFU 实际依赖游离在身份记录外。

分阶段验收，禁止用接口计划替代数值结果：

1. 描述符/Host单测：QKV几何、role/version、dtype/element stride、全部保留位、链循环、active窗口/liveness/freshness；未知内部ABI、8/9高位不alias旧kind；旧Host V与Qwen2描述符回归。
2. 实际Host Q/gate、K：M1/16先通，四组baseline/avx2 × cold/carried M128；所有输出BF16对独立官方/逐K oracle逐元素比较，guard bytes与最后ACK/publication检查，保留原有 V四组。
3. 独立新SFU owner的小有界真实RTL测试：Q/K各一head、tail原位、gate不变、gamma只加一次、partial64 split位置、BF16逐节点舍入；读错/写错/tag错误/backpressure/reset/数值域拒绝。
4. 7-command同一Host launch：前条输出只有在完成ACK后对后条可见；Q/gate→Norm→RoPE、K→Norm→RoPE和V都来自实际DDR写回；同一Matrix实例数、同一iDMA实例数；再升到四组M128。
5. 来源保留：用已验证code-pinned官方corpus的真实activation、Q/K/V weights、QK weights和显式trig生成输入；native结果只能作为比较oracle，不能注入owner输入。报告fresh/reuse分类与源hash，保留原native full-block failure，不改门槛掩盖它。

## 8. 这条闭包之后仍缺什么

该闭包最多证明生产Host的 attention-input前半段。完整Qwen3.5 block仍需单独闭包：QK/softmax/PV的Q宽2048而非hidden1024、KV与cold/carried实际状态/位置、attention输出sigmoid gate、O投影[2048,1024]、后续residual/FFN与完整原生数值门。

当前 `HostBlockCommands.scala:220-224` 仍以 `s.hidden` 绑定Q/PV；`Qwen2Block.scala:412-436` 相应attention寻址也用hidden。这些不能在本轮仅通过打开profile来误放行。已有SiLU owner是 FFN gate×SiLU 语义，不能当作attention sigmoid gate使用。

本文件保存原设计快照与最新有界进度；已执行结果仅按独立报告的M1 projection边界接受，Norm/RoPE及完整block仍是待执行计划。GDN作为并行生产Host主线推进。

## 审查快照的源文件SHA256

- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/HostBlockCommands.scala`: `5453796824bbb821a183cb51915ce1e61ab7d108e4f395903a18e6fe7c389630`
- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/HostBlockTop.scala`: `1f6d20bb4d098b7fbfbcc5e6288fefa65b9d7ab91ef9206723ae41f4a83433dc`
- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/QwenOwnerProtocol.scala`: `345027d7703ef51f4113b2ba9e648c23c88568566723c7ec61fbe033919b62fb`
- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/StreamingDense.scala`: `18d99633b57e5f394f99c242231a5ee009dcf125c03c8940674a01a7965ee789`
- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/MatrixPipeline.scala`: `dd1f3859ac65fa4d4839105cf166cb5d3a1f4d2d786991eb0f22749ad4ceca3d`
- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala`: `5120026fec639c2a6d85dfa4467e49e42b1996d6eb0a3d571d11bdda87688b5a`
- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/SharedMemoryArbiter.scala`: `6814e2f80890dbd5f5e8711eade58857deb690ab3c4c0fe9d5ea4ee8291ed6c6`
- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BurstProtocol.scala`: `0f2720e741af302952854b7787f63b4df55b9437048f818319f2cecf16034aac`
- `chisel/continuous_prefill/config/host_bf16_v_descriptor_contract.json`: `78bf6bb4cba70ae9ffd97c5a0c479e2c914f5fde6bd47b5db0ea3de3260901f5`
- `chisel/continuous_prefill/scripts/production_source_identity.py`: `18cbf3f423e2e1ab6baf5e098b28fa5454473984fbe32be55f7f5d260f00687a`
- `rtl/sfu/qk_norm256_bf16_candidate.sv`: `c87c8d1f6808d77a176adcba8b8fc4ed0cdd3ca5c3a9bc8b02e96acfc10a3362`
- `rtl/sfu/fp32_rmsnorm256_chunked.sv`: `aa86f362c4a82a3bce74b9c3e8466626b41c74b3af1691af117e5a9f63d95db4`
- `rtl/sfu/fp32_rope_pair_bf16_pipe_candidate.sv`: `dd73ae0939434d87ae939e4847c4c153fac2bddc3ecbd15321f316b1f470cfec`
- `rtl/integration/rope_bf16_l2_candidate.sv`: `c2c5cb39d0b367768208032f40f8a68d3a1b95f27579c9a11ac4bc4cd7b9aac4`
