# 五 profile M128：原生权重、驻留与供数必要界（源码审计，不是 RTL 实测）

## 结论先行

固定 **4096 Matrix MAC** 和完整 block 周期分母不变，用户 **至少 80%、争取 90% 以上**的目标不变。

1. 原始 Torch 参考 P3/P4 的 1024 条路由分别覆盖 **226/218 个不同 expert**。一个 expert 的 gate/up/down 三矩阵共 **6,291,456 B（6 MiB）原生 BF16**；不能只按 top-8 算整个 M128 block，也不能把 1024 条路由当 1024 份唯一 expert 权重。
2. 原生参数冷启动、无压缩、未在计时前预装、每个所需张量只取一次时，P3/P4 分别至少需取 **1,496,658,624 / 1,433,416,704 B**。在明确假想 **100×10^9 B/s、1×10^9 Hz** 下，仅此必要界给完整 block Matrix 有效利用率 **≤13.0548% / ≤12.4592%**。这不是实际频率/带宽/周期，更不是未来架构不可能达到 90% 的证明。
3. 当前选中路径不是持久 weight cache：选中 Dense B bank **80 KiB**，DMA mailbox **1 KiB**，B half 在每个 setup 重新装载；**流式请求禁用 mailbox 命中，且当前 Dense 每请求固定 1 个 64 B beat**。所以 `weightReadBeats=16` 不能解释为每个权重请求都合并成 16-beat burst。
4. 一个单 beat stream transfer 至少经过 `idle→issue→waitDma→reply→idle`，只计不同矩阵权重就有保守 `C ≥ 4N−1`。当前映射的权重传输单独给 P0/P1/P2/P3/P4 完整 block 利用率上界约 **25.2101% / 25.0001% / 25.7143% / 2.08869% / 1.99331%**。这是独立于时钟的源级必要界，仍无端到端 RTL 测量；P3/P4 条件于原始参考路由覆盖，不证明 DUT 路由相同。

**边界尤其重要：**本审计可证 root AXI 的取数路径，不能只凭源码中的“DDR”注释证明外部 LLC/互连/内存控制器一定不命中。把冷权重字节称为“物理 DDR 不可约量”需要额外系统契约。理想完全 warm-resident 的设计，其当次权重 DDR 必要量可为 **0**。

## 证据等级与便携复现

本包为 **HOLD、source-only** 审计与算术复现；没有新 DUT 测量、Torch 执行、EDA、硬件编辑或发布授权。

- 原始本地审计曾独立核对 8 个 safetensors header、70 个 receipt/native binding，读取两份各 8192 B 原始参考 route-ID 并只保留摘要。本包**不携带这些 headers、receipts 原件、权重、route IDs 或其他张量 payload**。`NATIVE_TENSOR_INVENTORY.json` 只含 70 个名称/shape/dtype/byte-count/修订号/既有 SHA 以及所需字节；默认复现信任这些已提交的摘要，不假装重新验证原始文件。
- `python verify_bounds.py`：重新计算全部70项形状字节、active-expert唯一量、五块完整Matrix-useful、mapped差异、冷/暖/端口/FSM必要界，并对照 `BOUNDS.json`。状态严格为 `PASS_SUMMARY_ARITHMETIC_ONLY_NOT_FRESH_SOURCE_OR_HEADER_VALIDATION_NOT_DUT`。
- `python verify_bounds.py --repo <repo>`：增加当前14份runtime/固定Commands源码SHA和已发布constructor helper SHA核对。它只证明本地源与pin相符，不是重新编译、header/payload验证或RTL测量。旧sparse checkout可用 `--fixed-commands <local-fixed-Commands.scala>` 显式指定同SHA固定文件；不允许悄悄退回历史Commands。
- 源 repo 相对路径与SHA见 `SOURCE_PINS.json`。固定Commands是 count-fix 版本；全部14份runtime pin和constructor helper均与已发布 `candidates/fixed_source_overlay_erratum_20261029/FIXED_SOURCE_OVERLAY_R2.json` 一致。沿用既有erratum已闭合的实际384MiB helper身份（SHA `8807829a…`）和既有class/high谱系证明；旧192MiB overlay声明已撤回，本包不把它重开为新硬件问题。
- 单测：`python -m unittest -v test_verify_bounds.py`；同命令可加 `-O`。建议OS设置256MiB地址空间上限。`VALIDATION.json` 记录本包实际执行的摘要算术、source-pin检查和轻量单测结果；不含私有路径。

## 1. 原生形状与唯一 expert 权重

下述矩阵用 checkpoint 原生 `[N,K]` 方向，provider 转为 `[K,N]` 仅重排，不增加原生信息量。

|profile|模型 / layer|投影原生 BF16 形状|FFN / MoE|
|---|---|---|---|
|P0|Qwen2-1.5B / 0|Q/O `[1536,1536]`；K/V `[256,1536]`|gate/up `[8960,1536]`；down `[1536,8960]`|
|P1|Qwen3.5-0.8B / 0|QKV `[6144,1024]`；Z `[2048,1024]`；a/b 各 `[16,1024]`；O `[1024,2048]`|gate/up `[3584,1024]`；down `[1024,3584]`|
|P2|Qwen3.5-0.8B / 3|Q `[4096,1024]`（含 Q gate）；K/V `[512,1024]`；O `[1024,2048]`|同 P1 FFN|
|P3|Qwen3.5-35B-A3B / 0|QKV `[8192,2048]`；Z `[4096,2048]`；a/b 各 `[32,2048]`；O `[2048,4096]`|下述 MoE|
|P4|Qwen3.5-35B-A3B / 3|Q `[8192,2048]`（含 Q gate）；K/V `[512,2048]`；O `[2048,4096]`|下述 MoE|

P3/P4 各自 layer 的 expert 原始两个 tensor：
- `experts.gate_up_proj` BF16 `[256,1024,2048]` = 1,073,741,824 B。每 expert 的前/后 512 行为 gate/up，**不重复计整个合并张量**。
- `experts.down_proj` BF16 `[256,2048,512]` = 536,870,912 B。
- 每 active expert：`2 × (1024×2048 + 2048×512) = 6,291,456 B`。等于 gate/up/down 各 2,097,152 B；当前 owner 用 `expert << 21` 定位每个逻辑矩阵。
- router `[256,2048]`；shared gate/up 各 `[512,2048]`；shared down `[2048,512]`；shared gate logit `[1,2048]`，均 BF16。

小参数亦按原生 dtype 精确计入：P0 两个 norm 与 Q/K/V bias 均 BF16；P1/P3 的 `A_log [16]/[32]` 与 `linear_attn.norm.weight [128]` 是 **F32**，conv `[6144/8192,1,4]`、dt_bias、两层 norm 为 BF16；P2/P4 Q/K norm `[256]`、两层 norm 为 BF16。P0/P1/P2/P3/P4 原生张量数 **12/14/11/18/15**，合计 70。除上述四项 F32 张量，其余全部 BF16。

|profile|Matrix-useful MAC|唯一原生矩阵权重 B|其他原生参数 B|合计 W B|
|---|---:|---:|---:|---:|
|P0|6,039,797,760|93,585,408|10,240|93,595,648|
|P1|2,755,657,728|43,057,152|53,856|43,111,008|
|P2|2,415,919,104|36,700,160|5,120|36,705,280|
|P3（226 experts）|8,002,994,176|1,496,584,192|74,432|1,496,658,624|
|P4（218 experts）|7,315,128,320|1,433,407,488|9,216|1,433,416,704|

Matrix-useful 沿用并独立复算完整 block 的 Dense + 矩形 attention MAC。一个乘加为一个 MAC；GDN/Scalar/Vector 工作不加入 4096 Matrix 分子；N1 只计有效一列。Attention masked future keys 仍用较宽松矩形口径；改用因果有效工作只会降低相同周期下的利用率。

## 2. 冷启动、warm 驻留、当前实现必须分开

设 `T` 为上表 Matrix-useful，`W` 为唯一原生参数字节，`R` 为在**所选测量边界内真实可复用且不会被驱逐**的原生有效驻留字节：

- **理想冷启动：**`B_weight ≥ W`，条件为所需值原本不在本地/外部缓存，按原生 BF16/F32 无压缩搬运，所有必要装载发生在完整 block 计时内。该下界忽略输出、activation、state、metadata、padding、重读、协议等，故只是必要条件。
- **理想部分 warm：**`B_weight ≥ max(0,W−R)`。若全部需要的权重真实驻留，权重 DDR 项下界为 0；但权重读端口、片上带宽、其他流量/算子仍可能限制性能。
- **当前 source：**80 KiB B bank 是 tile staging，不是能跨 job 命中的 expert/object cache；1 KiB mailbox 在 job 边界 flush，且 Dense stream 根本不走它的 hit 分支。因此不能从“物理 SRAM 中上次残留 bit”推断 warm 命中，也不能只从容量名推断流量。
- **外部层级：**本源集止于 root AXI。若 AXI 外还有 cache，DRAM 字节可能少于 AXI 字节；若预装在 block 计时前，则应明示 warm/preload 成本，不能同时报告 cold bound 和排除 preload 的周期。

“不可约”只相对于上述精度、表示、驻留和测量边界。未做信息论熵/可压缩性证明；没有授权量化；不能据本表排除未来缓存、有效复用、更宽/多通道供数、调度优化等设计方向。

## 3. 明确假想目标：100 GB/s + 1 GHz

`C ≥ f×B/BW`，故 `U=T/(4096C) ≤ min(1, T×BW/(4096×f×B))`。

在 `BW=100×10^9 B/s`、`f=10^9 Hz`、`B=W` 时：

|profile|仅冷权重最短时间 ms|权重 roofline U 上界|80% 必要有效 GB/s|90% 必要有效 GB/s|
|---|---:|---:|---:|---:|
|P0|0.93595648|100%（原始比值 157.55%）|50.779|57.126|
|P1|0.43111008|100%（原始比值 156.05%）|51.264|57.672|
|P2|0.36705280|100%（原始比值 160.69%）|49.785|56.008|
|P3|14.96658624|13.0548%|612.802|689.402|
|P4|14.33416704|12.4592%|642.097|722.359|

P0–P2 的 100% **只表示这个单一权重带宽必要条件不排除目标**，绝非实际利用率或达标。P3/P4 达 90% 的单 block 周期预算分别只有约 2,170,951 / 1,984,356 cycles，而冷权重供数至少约 14,966,586 / 14,334,167 cycles。未计其余工作，故差距至少如此。

同一个假想带宽/频率下，仅用 warm residency 消除这项瓶颈所需的**最低有效原生驻留量**：

|profile|80% 至少驻留 B|90% 至少驻留 B|
|---|---:|---:|
|P3|1,252,426,624|1,279,563,513|
|P4|1,210,176,704|1,234,981,149|

这是 `max(0,ceil(W−T×BW/(4096×f×q)))`，不是可实现容量建议；未计 replacement、port、ECC、其他 tensor 和足够高片上读带宽。不能用降低目标、改分母、降频数字游戏或把不同 block 的有效工作混入当前 M128 分子来声称达标。

## 4. 当前 owner/AXI/cache 的源级证据

下列 runtime 源采用 `SOURCE_PINS.json` 的 repo 相对路径；原本地审计曾与实际编译绑定对照，portable复现可重新验证源SHA，但不重编译。

```text
HostBlockTopV4
 ├─ QwenOwnerKernel
 │   ├─ TransposedDenseDownOwner（构造条件只选择这一种 Dense owner）
 │   │   └─ TransposedDownDenseBanks: A 688 KiB, B 80 KiB
 │   └─ MatrixPipelineService → 8 × RetainedMatrixEndpoint（4096 MAC）
 ├─ SharedMemoryArbiter(17) → 同一个 DMA（metadata/其他 owner）
 └─ RetainedIdmaWeightBurstAdapter(16, streaming=true)
     ├─ owner.burst 直接接 streamRequest（仍用同一个 DMA）
     ├─ mailbox: 16 × 512 bit = 1 KiB
     └─ RetainedIdmaBackend → 一个 512-bit BlockAxiMaster
```

|证据|可证明的内容|
|---|---|
|`DiagnoseOriginalHostMoePhaseV5.scala:105–111`；`HostBlockTopV4.scala:50`；`QwenOwnerProtocol.scala:235–247`|当前统一构造 `weightReadBeats=16,pipelined=true,enableTransposedDown=true`，只实例化一种 Dense owner；不是所有备选 owner/bank 的容量相加。诊断 emitter 中旧 admission 注释不能替代当前 runtime 源。|
|`TransposedDenseBanks.scala:148–149`|A = `16×1376×256/8 = 704512 B = 688 KiB`；B = `16×160×256/8 = 81920 B = 80 KiB`。这是声明存储位容量，不是 SRAM inference/PPA 已过。|
|`TransposedDenseOwner.scala:819,843–857,1037–1069,1114–1147`|选中 bank；原生 BF16 2 B；weight address 从 job.b 按 K/N 遍历；每个 burst 固定 `beats=1`、只允许一个 outstanding；每 setup 清 `halfReady`，从 DDR/AXI 重新加载 B half，无 persistent weight lookup。|
|`HostBlockTopV4.scala:38–40,51–53,306–330`|一个 AXI root；17 个逻辑普通客户端不是 17 个物理 DMA；Dense stream 和普通 arbiter 共享同一个 DMA；launch/job/done/FFN handoff flush。|
|`IdmaWeightBurst.scala:63–90,149–152,343–390`|16×64 B mailbox；`inWindow = !fromStream && ...`；stream 请求 count 用 `newStream.beats`，因此 Dense stream 永不 cache hit/prefetch；最终 backend response 后才能发布最后 beat。|
|`RetainedIdma.scala:7–38`；`IdmaWeightBurst.scala:124–139`；`BlockAxiAdapter.scala:5–12`|真实 retained backend ABI 与 root 均 512-bit；backend clock 接 root clock。这里只用 BlockAxi 类型，不把另一个 `BlockAxiMemoryAdapter` 误当本 root 选中的 adapter。|
|`UnifiedMoeRuntimeExpertLoopV4.scala:61–66,276–278`；`UnifiedMoeDenseWritebackV2.scala:25–48`|每 expert 三个逻辑原生 BF16 2 MiB 矩阵，expert stride `<<21`；不是按每 route 都重新算唯一参数量。|
|`HostMoeSharedGatePlanV5.scala:35–43,66–73,97–99`|逻辑 N1，物理 N32；实际 Dense 读取 padded image，useful 仍只 N1。|

**当前 AXI 接口容量：**至多一拍一个 64 B read beat，所以不论外部内存多快，都有 `C≥ceil(B_axi/64)`。只有在显式假想 root 1 GHz 时才对应 read 通道原始峰值 64 GB/s；不是实际可持续带宽，更不是宣称 DUT 实际跑 1 GHz。假想 100 GB/s 不能在“该单端口 + 该 1 GHz”的条件下通过，必须明确改变端口/频率/层级等条件，不能当当前硬件值。


同 clock 的独立 **64 B/root-cycle** 端口界（使用当前 mapped 唯一参数量；不含额外重复/其他数据流量）：

|profile|至少 root cycles|端口容量单独给出的 U 上界|
|---|---:|---:|
|P0|1,462,592|100.000000%|
|P1|673,610|99.875002%|
|P2|573,520|100.000000%|
|P3|23,387,275|8.354355%|
|P4|22,399,120|7.973170%|

该表与 100 GB/s 假想 roofline、下面 `4N−1` FSM 界分开；更快外部 DRAM 不能越过这个 root 端口。若端口表上界被截为 100%，同样不是达标证明。

## 5. 当前物理映射字节与单 beat FSM 必要界

- P0 **当前 corrected provider** 本地经校验的 corrected P0 provider（本包只保留其映射摘要）：七个矩阵保持 BF16，norm/bias 使用 exact FP32 storage（相对原生 +10,240 B）。旧 repo provider 曾描述矩阵扩大 FP32，**不适用于当前 corrected 路径**。
- P1/P2：transpose/AB concat 不改变元素数和 dtype；P1 dt_bias 为 32 B，64 B bus padding 等额外流量未加入下表原生唯一参数数。
- P3/P4：N1 4096 B 的数学权重对应实际 N32 131072 B image，替代计数 +126,976 B。未重复加读不参与 Dense 的逻辑 N1 metadata view；provider 里同时存在两种只读分配也不等于运行时两者都读 payload。

当前矩阵 weight stream 的无 hit 状态序列必须每请求走完 `idle,issue,waitDma,reply`；`ready` 只在 idle，single beat 的 last 不可提前转发。即便理想 backend 每状态只 1 cycle、无竞争/无 backpressure，N 次权重请求从第一次 accept 到最后 reply 也至少 `4N−1` 周期。完整 block 包含这个区间，故该不等式安全；实际 owner 请求准备、DMA 内部 AXI、激活/写回/其他算子只会增加周期。

|profile|当前 mapped 唯一参数 B|其中矩阵权重 B|最少矩阵 weight beats N|`4N−1` 周期下界|由此 U 上界|
|---|---:|---:|---:|---:|---:|
|P0|93,605,888|93,585,408|1,462,272|5,849,087|25.2101%|
|P1|43,111,008|43,057,152|672,768|2,691,071|25.0001%|
|P2|36,705,280|36,700,160|573,440|2,293,759|25.7143%|
|P3|1,496,785,600|1,496,711,168|23,386,112|93,544,447|2.08869%|
|P4|1,433,543,680|1,433,534,464|22,398,976|89,595,903|1.99331%|

表中的 mapped 唯一参数量不是全部 AXI 读字节或周期预测；当前 source 的规范遍历必需读这些矩阵元素，且不能复用旧 job 残留。P1/P3 既有 GDN serial 执行源界还有更紧限制（既有审计约 1.01796% / 1.26692%）。**独立 U 上界应取较小者，不能相乘；若要相加周期，必须先证明阶段互斥与流量/时间不重叠。**本审计未把新的权重界与 GDN 界直接相加。

## 6. 工程发现、验收与未闭合项

|编号 / 等级|发现与硬件后果|目标层次|机械验收|豁免条件|
|---|---|---|---|---|
|WB-01 / P2|Dense 64 B 单请求、无命中、单未决导致至少 4 状态周期/beat；`weightReadBeats=16` 并未实现选中路径的多 beat 吞吐|Dense owner → DMA stream|在统一新硬件上采真实 AR.len/R.fire、request outstanding、cache hit、weight bytes 与完整周期；与源码预期对账|仅作为现有正确性基线、明确不声称性能达标|
|WB-02 / P2|80 KiB B staging 无跨 job 有效驻留，不能支撑 1.4–1.5 GB cold working set 的“warm cache”假设|B banks / cache validity / dispatcher|固定 source SHA；连续 block + expert-set 变化 + job/epoch 切换测试，验证 hit 身份/valid/失效和真实 DDR/AXI 读量|只采用明确 cold 条件，不宣称驻留收益|
|WB-03 / P2|100 GB/s 与当前单 512-bit root@假想 1 GHz 不相容，且外部 DDR 层级未定|root interface / memory integration|给实际时钟、端口数、clock-domain、有效带宽、外部 cache policy；测量 AR/R 与内存控制器 counter|100 GB/s 仅作为未来目标 roofline，不能当当前值|
|WB-04 / P3|native、mapped padding、cache preload、完整周期口径容易混用|bench / perf counters|分别记录 cold/warm、所有权重/activation/state/metadata bytes、固定4096周期、useful MAC 与 causal/rectangular口径|无性能结论的输入 transport 测试可不做性能签核|

分项结论：
- **功能数值：未签核。**原始 Torch active count 不能冒充 DUT route equality；未重新执行 Torch 或全 block RTL。
- **协议：未签核。**本次只从状态机推保守必要界，没有执行错误/背压/retire 协议测试。
- **物理实现：未签核。**声明容量/接口宽度有源码证据，无 SRAM/DSP inference、STA、面积功耗结果；外部实际 DDR/LLC/频率契约未知。
- **QoR：当前 source 的必要界已足以否定“当前已接近 80/90%”的说法，但不否定未来统一架构。**保持目标，用实测校准并在统一变更后五块重测，不继承旧 PASS。

包状态为 HOLD，未 push。仍需外部证据而非本次可执行范围：实际系统 memory hierarchy/clock/bandwidth 契约，以及同一新统一硬件的全 block RTL counter trace。不是因为暂时没有这些证据就降低目标。

## 7. 保持 80/90% 目标时必须改变或证明的条件（本次未应用任何改变）

- **burst / outstanding：**当前 stream `beats=1` 和单未决 DMA 至少一项必须重新设计，才可能消除本文的 4N−1 权重串行界；仅修改 maxBeats 参数或理想 memory 响应延迟不够。多未决方案需真实 tag/credit/错误 drain/唯一 retire 证明。
- **有效驻留 / reuse：**若仍用 100 GB/s + 1 GHz 假想条件，P3/P4 的本次 frozen 输入 cold 权重差距必须由可验证的有效驻留/合法复用等减少，或提高供数；必须同时给缓存身份、容量、端口、替换和预装计时契约。
- **root 带宽：**任何超过 64 B/root-cycle 的有效 read 目标需更宽/更多端口或已验证的不同 clock-domain 设计；不能把外部 memory 广告带宽直接赋给当前 root。
- **统一算子调度：**上述供数条件只是必要条件，仍需解决已审计的 expert 小 M 几何浪费、QK 映射、GDN 串行链与其他完整 block 开销。五 profile 必须在同一统一硬件重测。
- **精度与指标不变：**本次没有更改算术、舍入、dtype、固定4096或完整block分母；不降低90目标。226/218 是所钉住输入的原始参考分布，不是所有 MoE 输入的普适限制。
