# Qwen2 完整预填充：片上驻留与固定资源条件审计

本文于 2026-10-11 根据工作区基线 `5ca2b5cf8c948f9a5e193e462b0ddc9f3a65fbd0`
及当日待发布的流量脚本作源码审计。没有实现候选硬件，没有运行新的模型、测试、
Chisel、RTL 或 EDA。文中的下界、容量候选和实测结果必须分开使用。

结论是：在相同 768 KiB Dense 数据 SRAM 容量内，存在减少权重重读、将 FP32
部分和保留在片上的容量候选。但现有模块没有所需的部分和恢复接口和路由。
维持当前 Host Attention、Scalar 和 Vector 调度时，即使 Dense 理想化，完整
M128、M1024 请求也不能达到 80% 利用率。不能将容量够用或流量减少写成性能达标。

## 适用后端与计数口径

本文的 Host 条件界固定为真实 Qwen2 几何 H1536、F8960、12 个 Q heads、2 个
KV heads、head dimension 128、单批次、无历史缓存的因果预填充。配置为
`HostBlockTop`、4096 MAC、16-beat 权重读、`PIPELINED_OWNER=1`。

- 外部普通 Dense 的 A 和 D 均为 FP32，每元素 4 B；权重 B 使用 BF16，每元素
  2 B。A 在私有 SRAM 中经 RNE 存为 BF16，每元素 2 B。
- 片上 A 为 BF16，不代表当前 Qwen2 Host 已支持外部 BF16 A/D。后者需要新增
  命令类型约束、生产者存储策略及数值验证，本文候选外部流量没有采用这种优惠。
- 利用率始终为完整请求 useful MAC /（4096 × 完整请求周期）。停钟、空闲切片、
  Scalar、DMA、Vector、依赖等待和写回确认不能从分母删除。
- Host 的 SiLU 使用 16-lane `VectorSiluOwner` 或 `OverlappedSiluOwner`；后者
  只重叠同一 owner 内的内存与计算。不能套用 autonomous core 的单元素 SiLU。
- 非流水 Host、autonomous core、已有 16-lane 功能后端不适用本文的调度公式。
  尤其不能给 16-lane 功能后端套用 4096 的资源身份，或把其合成 M16 回执当作
  本文候选的硬件证据。

当前可执行条件界见 [流量脚本](../scripts/qwen2_prefill_traffic_bound.py)。默认
输出只检查权重流量；`--host-schedule` 加入现有 Host 的串行算术计数。两种输出
均保留 `predicted_full_block_cycles`、`rtl_measured_cycles`、
`rtl_measured_utilization` 为空，不构成硬件验收。

## 当前 SRAM、行组与状态账本

`DenseScratchGeometry` 固定分配如下：

| 数据区 | 分配 | 字节 |
|---|---|---:|
| A | 16 banks × 1376 words × 32 B，BF16 打包 | 704,512 |
| B | 16 banks × 160 words × 32 B，双缓冲、K16、5 个 N 槽 | 81,920 |
| 合计 | 已分配完的 768 KiB | 786,432 |

每个 16 行 M tile 在每个 A bank 中占 K/16 个 words。

| K | 每 tile 的 bank stride | 当前 M tiles / 行数 | 有效 A | 已分配但未用的 A | 当前有效双 B | B 保留未用槽 |
|---|---:|---:|---:|---:|---:|---:|
| 1536 | 96 words | 5 / 80 | 245,760 B | 458,752 B | 16,384 B | 65,536 B |
| 8960 | 560 words | 2 / 32 | 573,440 B | 131,072 B | 32,768 B | 49,152 B |

K1536 的 A 容量按整 tile 本可容纳 `floor(1376/96)=14` 个 tile，即 224 行，
当前 80 行主要受 5 个 accumulator contexts 限制。K8960 则受容量限制：
`floor(1376/560)=2`。即使重分配 B、只保留一个 N tile 的双缓冲 16,384 B，
A 最多为 1504 words/bank，仍只能放 32 行；48 行仅 A 就需 860,160 B。

这些闲置区已经属于特定银行、深度和地址映射，不能直接当作可供其他端口同时
访问的自由容量。80/32 是现有调度的行组容量，不是所有同容量调度的最优性证明。

768 KiB 不包含 Matrix 的累加器或结果寄存器。可以直接从源码识别的其他数据
寄存器包括：5 组 accumulator 共 81,920 B、各 lane 的结果队列共 81,920 B、
`MatrixResultFifo` 32,768 B、Dense 的 `finalValue` 16,384 B，合计至少
212,992 B；流水寄存器、控制和其他队列还要另计。

此外，现有 Qwen2 core 声明 573,440 B 的 `SharedL2Fabric`，elementwise 声明
12,288 B，scores/probs 声明 8,192 B。这些显式数据 SRAM 与 Dense 合计
1,380,352 B。该数是源码数据 SRAM 小计，不能充当包含所有队列、寄存器、宏映射
结果的物理总存储证明。它们还是独立实例，当前 Dense 不能免费访问。

## 当前调度的严格条件界

七个 Dense 矩阵共 D=46,792,704 个权重元素，其中 down 为 13,762,560。
记 token 数为 M，P=12×M×(M+1)/2，则：

- Dense useful MAC = M×D。
- QK/PV useful MAC = 256×P。
- 当前 BF16 权重读字节 = 2×[(D−13,762,560)×ceil(M/80)
  +13,762,560×ceil(M/32)]。
- 一个 512-bit AXI R 口每周期最多接收 64 B。流式读取不会命中适配器的权重小缓存。

| 工作量 | 当前权重入口字节 | 权重读周期下界 | 仅权重给出的全请求利用率上界 |
|---|---:|---:|---:|
| M128 | 242,221,056 | 3,784,704 | 38.79997% |
| M1024 | 1,739,587,584 | 27,181,056 | 44.48604% |

现有 Attention 的 `sliceMask=1`，QK 取对角、PV 取 row0，单请求在途。每对
head/query/key 的 QK 和 PV 各发 8 次请求，每次只有 16 useful MAC。
即使每次 Matrix 请求只花 1 周期，Attention 也至少需要 16P 周期。

再将每次 scalar primitive 都极度乐观地视为 1 周期，包括 exp、div、sqrt，
当前互不重叠的操作如下：

| 当前 Host 操作 | 周期下界 |
|---|---:|
| QK/PV Matrix 请求 | 16P |
| QK 16 项归约与缩放 | 17P |
| softmax 差值、exp、求和 | 3P |
| softmax 倒数 | 12M |
| PV 对 8 个列块重复的概率乘法 | 8P |
| 两次 Norm 的 scalar 与 16-lane vector 运算 | 3656M |
| QKV bias | 128M |
| Q/K RoPE | 336M |
| 两次 residual | 192M |
| 16-lane SiLU，每组 16 元素的 6 个串行 primitive 阶段 | 3360M |

因此当前非 Dense 算术下界为 `44P+7684M`。Norm 项具体为两次各 H1536 的
顺序标量归约、每行 4 个后续 scalar 请求，以及每 16 元素 3 次 vector 运算。
这里没有把一个 head/query/key 对本身重复算作额外操作。

`QwenOwnerKernel.active/mode` 使 Dense、core 和 SiLU owners 串行，故这些
非 Dense 周期可以与 Dense 下界相加。SiLU 内部内存重叠不改变这个事实。

| 工作量 | 非 Dense 下界 | Dense 理想时全块利用率上界 | 当前 Dense 权重界加非 Dense 的周期下界 | 当前全块利用率上界 |
|---|---:|---:|---:|---:|
| M128 | 5,342,720 | 21.57922% | 9,127,424 | 16.08848% |
| M1024 | 284,962,816 | 4.07596% | 312,143,872 | 3.87378% |

真实算术延迟、握手、KV 复制、metadata、非 Dense 内存、Dense A/D 流量及阶段
排空均未计入。即使完全省略所有 Scalar/Vector，只保留当前 Attention Matrix
请求与理想 Dense，M128/M1024 也分别只能得到 48.18706%/10.75209% 的乐观上界。
这些结论约束保留当前非 Dense 映射的方案，不是对所有固定资源新调度的否定。

## 候选一：M128 全 A 与单 N tile 部分和驻留

候选固定 Ntile256、KC256，把原两组 Dense SRAM 改划为：

| 物理数据区候选 | 容量 |
|---|---:|
| 16 banks × 1024 words × 32 B，放 A/C | 524,288 B |
| 16 banks × 512 words × 32 B，放双 B | 262,144 B |
| 合计 | 786,432 B |

银行数量和每 bank 位宽不增加，但深度、逻辑分区和路由改变。当前代码没有这份
映射；相同总字节不证明宏选择、面积、布线或时序已经闭合。

对于 K1536 的 Q/K/V/O/gate/up：全 M128 A 为 393,216 B，当前 Ntile 的
FP32 C 为 131,072 B，双 B 为 262,144 B，峰值正好 786,432 B。
先加载全 A，再遍历 Ntile；每个 Ntile 内按 KC 递增，遍历 M tiles。

对于 K8960 down：A 的 KC 块为 65,536 B，C 为 131,072 B，双 B 为
262,144 B，有效数据峰值 458,752 B，固定物理分配仍为 786,432 B。
按 Ntile、KC、M tile 的顺序计算，A 被 6 个 Ntile 分别重读。

C 是同一个递增 K 累加过程的 FP32 快照。恢复后必须继续原 FMA 顺序。
独立计算各 K 块再相加会改变舍入顺序，不能用来冒充等价恢复。

七个 Dense 的完整数据流为：

| 传输 | M128 字节 |
|---|---:|
| 外部 BF16 权重读取，每矩阵一次 | 93,585,408 |
| 外部 FP32 A 读取，前六矩阵各一次、down 六次 | 32,243,712 |
| 外部 FP32 最终 D 写入 | 11,796,480 |
| 外部部分和读写 | 0 |
| 片上部分和恢复读取 | 81,788,928 |
| 片上部分和保存写入 | 81,788,928 |
| 外部总 R+W | 137,625,600 |

部分和每方向字节为 `4M×Σ[N×(ceil(K/KC)−1)]`；首个 K 块从零累加，
最后一个块直接产生最终 D。全 A 驻留不会自动消除不同 Dense 命令之间的 A
重复加载；上述数字没有假设跨命令融合。

现 IDMA 的外部读写由一个请求状态控制、不能同时传输。因此只算外部数据已需
至少 2,150,400 周期。Dense 的理想算术需 1,462,272 周期。前一个数字是
条件下界，不是候选预计用时，也没有把片上部分和当成零成本。

## 部分和接口：64 B 与理想 512 B 两种条件

当前 Matrix 结果确实为 16×256 个 FP32，但 Dense 的现有写回扫描每拍只生成
64 B，见 `outputPacket`、`writeRow/writeBeat`。宽结果寄存器本身不能证明
checkpoint 能以 512 B/cycle 保存。当前 `MatrixStreamStep` 也没有 FP32 seed
字段，lane 只能从零或原 context 的 accumulator 继续，恢复入口尚不存在。

| 假定有效搬运带宽 | M128 恢复读取下界 | M128 保存写入下界 | 两方向都串行时合计 |
|---|---:|---:|---:|
| 64 B/cycle，每拍一个现有宽度的数据包 | 1,277,952 | 1,277,952 | 2,555,904 |
| 512 B/cycle，新增并行 bank 路由后的理想聚合值 | 159,744 | 159,744 | 319,488 |

两行都假设每周期有效搬运、无空泡。64 B 行也只是接口条件：当前还没有通往
C SRAM 和 accumulator seed 的完整传输通路。512 B 行需要显式设计同时访问
16 banks 的路由、地址选择、字节使能与 seed 写入选择，不得当作现有吞吐。

保持现有 bank 和 accumulator 写口数量时：

- C 恢复与 A 操作数读取共享 A/C SRAM 读口；不能在同一 bank 上免费同时读。
  沿用每个 MAC step 一次 A 读取时，完整请求至少要支付所有 A 读次数加 C 读次数。
- 将 C 写回物理 accumulator 要与 FMA 返回写回仲裁。保守方案先排空流水，暂停
  Matrix，再通过同一写口的选择器恢复；增加第二写口不在本候选授权资源内。
- C 保存可能与另一个 context 的计算重叠，但必须证明原 SRAM 读写口能并行、
  结果缓冲不会被覆盖、A/B 加载没有端口冲突，而且最后一次写已经确认。
  本审计未证明这种重叠，不把两方向成本全部隐藏。
- 可以考虑复用现有 `finalValue` 和结果队列暂存，但其占用、排空和生命周期必须
  纳入模型；不能同时给多个用途各算一份免费缓冲。

令 C算术=1,462,272、C外部=2,150,400。若恢复与计算不重叠，则条件下界为
`max(C外部, C算术+C恢复)`；若保存也暂停计算，则使用
`max(C外部, C算术+C恢复+C保存)`。

| M128 接口条件 | 恢复阻塞计算时 Dense 下界 | 两方向都阻塞计算时 Dense 下界 |
|---|---:|---:|
| 64 B/cycle | 2,740,224 | 4,018,176 |
| 理想 512 B/cycle | 2,150,400 | 2,150,400 |

这些较宽松的下界仍没有包含 seed/command 额外握手和实际 FMA 回授延迟。
它们给保留当前非 Dense 调度的 M128 全块上界分别为：64 B 恢复阻塞时
18.16744%，64 B 两方向阻塞时15.68722%，理想512 B时19.59750%。不能从
下界反推实际性能必然改善；较慢的部分和接口甚至可能抵消权重读取收益。

## 五个物理 contexts 与八个 M tiles

M128/N256 的 8 个 M tiles 不等于新增 8 组物理 accumulator。本候选把其
131,072 B 状态放入已计入容量的 C SRAM，分批轮换现有 5 contexts。
5+3 尾组、每次恢复、流水排空和 context 再次可用的等待都需要计时。
只按4096 MAC/cycle计数仍是乐观极限，不能保证每拍满载。

现有 `rows/capacityRows` 的 7-bit 范围、tile 索引、合法 context 检查、组结束
协议和 `clear` 语义均需调整。控制寄存器位数、选择器、路由和仲裁必须显式记账；
本文没有证明这些逻辑无需增加面积或状态。

另一条路线是直接把物理 accumulator 从5组扩到8组。仅增加的 FP32
accumulator 就需 `3×4096×4=49,152 B`，另有 valid/busy、选择器和调度成本，
因此不属于零状态成本的复用。即使只做这一步而保持现有 A/B 分配，down仍只容
32行；M128/M1024仅权重界也分别最多53.34996%/54.91246%，仍不能满足80%。

## M1024：分组、分块与其他 SRAM 的边界

K1536 的 M1024 全 A BF16 需要3,145,728 B，超过前述显式数据 SRAM 小计。
因此“M1024全 A 驻留”不成立。以下两个候选都仅使用Dense原768 KiB总容量，
仍保持外部A/D FP32，外部partial为零。

| 候选 | 同时有效 A/C/双 B | 权重 R | A R | D W | 片上 partial 每方向 |
|---|---|---:|---:|---:|---:|
| 8个Mmacro128，复用前述KC256方案 | 与M128相同，峰值786,432 B | 748,683,264 | 257,949,696 | 94,371,840 | 654,311,424 |
| 2个Mmacro512，KC128、N256 | 131,072 / 524,288 / 131,072 B | 187,170,816 | 748,683,264 | 94,371,840 | 1,402,994,688 |

第一种的外部R+W至少17,203,200周期，第二种至少16,097,280周期。第二种虽然
权重读更少，但A必须按Ntile重读，并且片上partial更多。

对Mmacro128方案，partial每方向在64 B/cycle下需10,223,616周期，在理想
512 B/cycle下需1,277,952周期。M1024理想Dense算术为11,698,176周期。
若恢复和保存均阻塞计算，两个带宽条件分别给出Dense至少32,145,408和
17,203,200周期，后者由外部流量主导。

对Mmacro512方案，每方向partial成本在64 B/cycle下为21,921,792周期，
理想512 B/cycle下为2,740,224周期。任何宣称它优于前一候选的周期模型都必须
同时算入这一变化、现有五contexts周转和新路由成本。

若将独立core/elementwise数据SRAM重新共享，M1024、KC96、N256在容量上可
放下A196,608 B、C1,048,576 B和双B98,304 B，共1,343,488 B。其外部R+W为
936,640,512 B，至少14,635,008周期；片上partial每方向1,906,311,168 B。
但这需要跨owner的存储所有权、地址映射和端口仲裁改造。原P0 fabric的两个
64 B读接口、一个64 B写接口及bank冲突规则不能免费变成Dense的512 B接口。
这个数值只证明存储容量候选，没有证明其控制、端口或时序实现可行。

## 后续模型需要关闭的条件

1. 保持原FP32部分和并按递增K继续FMA，对照原数值模型；不可用分块结果相加
   替代seed恢复。新的外部BF16 A/D策略需要独立列项，不能混入当前流量。
2. 固定每个物理bank、端口、队列和accumulator状态的归属，按阶段证明可以
   时间复用。重新分区不增加总字节，也不等于物理宏和布线成本已经通过。
3. 对64 B checkpoint接口与新并行路由分别计算种子恢复、保存、排空、仲裁、
   五contexts回授和最后写确认；不要只统计DDR权重读。
4. 将当前Qwen2 Attention映射、Norm、RoPE、SiLU、residual和完整依赖串行
   纳入相同周期模型。Dense驻留改造不能单独证明完整请求80%或90%。

## 主要源码依据

- [DenseReadPlanner.scala](../chisel/continuous_prefill/src/main/scala/heteronpu/continuous/DenseReadPlanner.scala)：12–20行固定容量及行组选择。
- [StreamingDense.scala](../chisel/continuous_prefill/src/main/scala/heteronpu/continuous/StreamingDense.scala)：47、61行银行；123行A读取；175–226行结果与64 B写回；234–236、301–322行分组循环。
- [HostBlockCommands.scala](../chisel/continuous_prefill/src/main/scala/heteronpu/continuous/HostBlockCommands.scala)：423–424行普通Dense A/D FP32与BF16权重许可。
- [BurstProtocol.scala](../chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BurstProtocol.scala)：24–27行当前Matrix输入没有FP32 seed。
- [MatrixPipeline.scala](../chisel/continuous_prefill/src/main/scala/heteronpu/continuous/MatrixPipeline.scala)：61–69行八个切片和五contexts限制。
- [lane RTL](../rtl/matrix/candidates/rev8b_b/bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv)：15、32–37、55–59行accumulator状态及单条更新路径。
- [QwenOwnerProtocol.scala](../chisel/continuous_prefill/src/main/scala/heteronpu/continuous/QwenOwnerProtocol.scala)：67–70行Host算术选择，115–119、295–337行owner与共享Matrix串行。
- [Qwen2Block.scala](../chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala)：119–123、180行独立SRAM；151–173、438–463行Attention映射；289–304、425–437、487–490行其他算术。
- [VectorSilu.scala](../chisel/continuous_prefill/src/main/scala/heteronpu/continuous/VectorSilu.scala)与[OverlappedSilu.scala](../chisel/continuous_prefill/src/main/scala/heteronpu/continuous/OverlappedSilu.scala)：16 lanes、六个串行primitive阶段及owner内部重叠边界。
- [ElementwiseMemoryEngine.scala](../chisel/continuous_prefill/src/main/scala/heteronpu/continuous/ElementwiseMemoryEngine.scala)：53–58、106–120行residual的16-lane向量执行。
- [IdmaWeightBurst.scala](../chisel/continuous_prefill/src/main/scala/heteronpu/continuous/IdmaWeightBurst.scala)：62–65、123–134、191–199行外部读写互斥，330–355行stream不命中权重缓存。
- [SharedL2Fabric.scala](../chisel/p0_safety/src/main/scala/heteronpu/p0/SharedL2Fabric.scala)与[LocalSramConfig.scala](../chisel/p0_safety/src/main/scala/heteronpu/p0/LocalSramConfig.scala)：P0实际银行容量、接口和冲突仲裁。

Host条件界依赖的哈希集合由流量脚本检查。本次交叉审查将Host集合从25个文件
补全到27个，新增residual实际执行路径的`ElementwiseMemoryEngine.scala`
以及定义内存请求、向量块配置的`Protocol.scala`；工作流触发路径同时覆盖两者。
默认仅权重报告仍检查原23个文件，输出口径不变。最终27个哈希均与审读源码一致；
本文没有重新运行父任务已报告通过的11项测试。本文读到的新增重要依据哈希为：

| 文件 | SHA256 |
|---|---|
| ElementwiseMemoryEngine.scala | cb8a338051cce94dda613603df892bd0f43b6ea62423ad1f9d28b24f98b73845 |
| BurstProtocol.scala | 0f2720e741af302952854b7787f63b4df55b9437048f818319f2cecf16034aac |
| SharedL2Fabric.scala | 10372482417b8802fcf494e10af6a8d202e1dc5bb39d1a637d27da259efa30c5 |
| LocalSramConfig.scala | 6d8167530ae045ca038f644a93238731d6f2b645a01cf856d1ab111387de0464 |

任何上述映射、端口、算术顺序或owner串行关系变化，都需要重新审计相关条件界。
