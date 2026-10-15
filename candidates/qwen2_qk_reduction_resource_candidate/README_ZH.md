# Q/K 8×8 归约的固定资源调度审查

状态：**仅整数调度/容量检查通过；不是硬件 PASS。** 本目录不执行张量数值、
官方 oracle、C++/RTL、CI，也不修改旧候选/runner/门限。`sources.json` 冻结十个
只读证据源。`screen.py` 不调用其他候选执行入口。

## 先给结论

不必把每个输出的 64 个 partial 同时映射到 64 个 context，更不能假定
64 路 K 输入免费并行。可让 5 个真实 context 各承载一个 partial p，沿用
16M×256N 外积，完成 p 后落到已有 A SRAM，再做精确树。这是可执行的
整数依赖/地址计划，**尚无接通的 feeder、spill/tree 控制器或时序证据**。

这个映射每个已接受 Matrix issue 有 4096 个有用 FMA，几何填充为 1.0；
代价转移到大量 FP32 partial 搬运、共享 16 路 Add 和重读权重。1.0 不代表
利用率或吞吐率。在本文默认假设下，Q/K 投影核心的串行账本为 9,520,072
服务单位，条件 MAC 比率约 0.9035%；它不是周期预测，更不是性能实测。
性能结论保持 NO-GO；不能因为后续数学逐位一致就接受这个成本。本批仅提供
可复核 screen，不扩为架构实现，也不引入 FP64 或新增 MAC。

## 实际源资源与边界

- `MatrixPipeline.scala:61,68,94-100`：8 个原 16×32 endpoint，context 0..4；
  所有叶的 A16 是同一个向量，B256 按 32 列切分。没有新增 MAC。
- `bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv:15-16,32-40,55-61`：
  每单元 5 个 FP32 accumulator 和另 5 个 result registers。它们是不同资源。
  4096×5×4=81,920 B accumulator；叶 result registers 也为 81,920 B。
- `MatrixPipeline.scala:7-22,49-58`：2 个 16 KiB 结果 FIFO，8 个 metadata slots。
  FIFO 只负责返回 credit，不能复用成额外 accumulator contexts。
- `StreamingDense.scala:47-61,72,123-138,260-275` 与 `DenseReadPlanner.scala:12-18`：
  A=16×1376×32=704,512 B；B=16×160×32=81,920 B；另有一个 16 KiB
  finalValue。A 每银行单读单写，输入搬运有单银行选择；原生 B 64B 搬运可写
  两个不同银行。A/B 容量来源与当前软件 fullblock 的 transposed 映射要区分。
- `ffn_attention/matrix_service.py:1-16,source_identity`：模型只借同一
  accum[5][16][256]，协议 tick 不等于硬件 cycle；借用路径默认关闭。
- `ElementwiseRegisterLoan.scala:27-39,49-58,75-100`：可借已有 16 路 Add，
  只在原 Elementwise 空闲且 drain 后接受，一次事务独占；当前 Qwen2 profile
  并没有接通本目录树 borrower。禁止额外实例化第二组 16 路/63 路加法器。
- `kernel.cpp:49-64` 是算术图来源；这里仅验证图形结构，不验证浮点结果。
- 已 tracked 的 `qwen2_official_platform_fullblock/runner.py:293-314` 固定原完整 block useful MAC 为
  6,014,828,544。它是工作量证据，不能把软件事件数/CPU 时间当硬件分母。
  不依赖未发布的本地 recovery runner；source checker 只读 AST 核对该常量，
  不 import/执行完整 block。十个 source pins 均来自已 tracked 的仓库源。

## 最小分组方案与精确数据次序

串行 Q、K；各自按 M16 和 N256 tile 遍历。Q 为 8×6=48 tiles，K 为 8×1=8。
对一个 tile，定义 p=8r+lane，r,lane 均为 0..7。

1. 用 `full_tree()` 构造原 register offsets 4,2,1，再 lane offsets 4,2,1
   的有序二叉树。左右操作数保持原位；不交换、不重结合。
2. 深度优先叶序起始为 0,32,16,48,8,40,24,56,4,36,20,52,12,44,28,60。
   全 64 叶序在 `schedule()['leaf_order']`。这一顺序只改变相互独立叶的
   执行时刻，不能改变某一叶内部 t=0..23 的 FMA 顺序。
3. 每组最多 5 个 p，context c 对应该组的 p[c]。按 t-major、c-minor 发
   k=64t+p[c]，t=0 时 clear，t=23 时 last+emit，仅最后 context 置 finish。
   每次 A16 是 16 个 token 在同一个 k 的值；B256 是同 k 的 256 列权重。
   每个输出一直留在同一 physical row/column，通过 context 选择 p。
4. physical_col=32*slice+leaf_col，slice=0..7、leaf_col=0..31。
   **同一输出的 64 个 p 在时间/context 上展开，绝不在 8 个叶之间横向加和。**
   8 个物理叶各自覆盖不同 N 列，返回拼接保持 `MatrixPipeline.scala:99-100`
   的原坐标。所谓 register/lane tree 是逻辑 p 图，不是横向折叠 N 列。
5. 每组全部 partial 先从现结果返回通道落到本地 slot，再按 postorder 执行
   已就绪树节点。13 组为 12×5+4；尾组 4 contexts 有真实 recurrence 空位。
   理想 operand-ready issue span 每组 `(24−1)*max(contexts,5)+contexts`，
   再单独计 fill/drain；其他 stall 不能删掉。
6. 最终根再做原 `+0.0f`。根保持 FP32，交还候选选择的原 raw 输出边界；
   Bias 和 RoPE 不在这里融合、重排、提前取 BF16 或改 rounding。

## 活跃存储、地址和端口

符号 allocator 验得最大 **10×16KiB=160KiB** live partial；保守预留 11 个
slots=176KiB。单纯深度优先可只留 6 层栈，但分组 5 个 leaf 先落地，不能
拿 6 个 slots 冒充本分组计划的峰值。也不需要把 64×16KiB=1MiB 全留在片上。

A 完整保守 reservation：

- 原 M128×K1536 BF16 激活：393,216 B（384KiB）
- 11 个 FP32 partial slots：180,224 B（176KiB）
- 合计 573,440 B（560KiB），A 余 131,072 B（128KiB）

因此没有把 A 当空闲区，也没有把原激活覆盖掉。本最小流程实际每次只需 M16
输入；保守 reservation 连完整 M128 激活也保护。当前 StreamingDense 最多
缓存 M80，并不因此自动获得 M128 输入模式；新控制器可继续只用 M16，不靠
M128 缓存支持或其权重复用获益。下游/其他 owner 必须独占同一 A/B lease，
其同时活跃内容若不能释放，需重新做全局 liveness，不能凭本容量表签字。

每个 A bank 0..767 行保留原全激活。slot s 的 packet j（16 FP32）分两段：
`linear_word=2*j+half; bank=linear_word%16; row=768+32*s+linear_word//16`。
11 slots 占行 768..1119，低于 1376；实际不是新分配 SRAM。

- 64B packet 在两个不同 bank，各用一个 32B word。
- 同 packet 的 lhs/rhs 映射到相同两个 bank，必须先读 lhs，再读 rhs，随后写。
  数据流量是 2×64B 读+1×64B 写，但原 A 控制全局只选一个 bank 写，故明确收
  **2 个读阶段+2 个32B写阶段**。不假设新增双bank写带宽或两个读端口。
- 一次保留 64B lhs packet 的暂存（已显式列为新增 bounded hold），rhs 走
  已有读响应/借用输入握手。不能隐含额外 16KiB transpose 或临时结果 tile。
- Add 结果覆盖 lhs 的**当前 packet**，其余未读 packet 不动。借用引擎保持其
  现有64B结果，直到两个32B分写都接受；不得先 result.fire 再无存储地等待。
  rhs slot 仅在 256 packet 的512次32B写入全部确实提交后释放。
  A SRAM 本身没有外部 DDR ACK：
  “本地写 ACK”在计划中指新路由的实际写接受/提交收据，不是等待固定时间。
  新 owner 必须提供可验证的提交围栏，不可假称已有 ACK 接口。

B 放一组 `5×24×256×2=61,440 B`，bank=n//16、row=5*t+c、lane=n%16；
120 行/银行，容量 160。两组同时需 120KiB，超过 80KiB，所以本计划彻底
串行 refill/compute，**不拿原两个 K16 半缓冲推导重叠收益**。改变 B 的分区/
地址控制不可避免；现 feeder 不能直接接受这个地址计划。

A/B 之外保持现有 accumulator 80KiB、叶 result registers 80KiB、结果 FIFO
32KiB、finalValue 16KiB，并另外列 64B lhs hold；未把这些重复计作可用 spill。
地址 mux、tag、slot 状态、arbiter 和新增布线面积/时序均未量化。

## 协议/ACK 清理要求

所有发出计数只在 valid&&ready 更新。p、context、M/N tile、group epoch、
tree node、packet index 随事务携带，不能用当前 issue counter 代替返回 tag。

- Matrix 只复用 5 个合法 context，不改变 accumulator clear/last 契约。
- 原 2-result FIFO 可能背压；`result.ready` 仅在 finalValue/落地路由有 credit
  时拉高，不能先收后丢。未 emit 的中间结果仍需正常消费、释放叶 result FIFO。
- 下一组不能覆盖仍活跃的 slot。必须等 Matrix done 和已接结果写完；Vector
  borrower 空闲、所有借出请求/result 退休，且本地写提交全部匹配。
- 树每个 slot 有 live/sealed/node/epoch 状态。in-place lhs 更新期间禁止对外
  发布；错误使整次 owner 失败，必须 drain in-flight 数据与结果，不能把半写
  lhs 当旧有效内容继续使用。异常解除需要协调 reset/drain，不能靠计时器。
- 只有最终 raw tensor 的所有 DDR 写数据与匹配 tag/byte ACK 均完成后，才能
  发 owner terminal/public completion；Bias/RoPE 继续其原各自 ACK/发布边界。
- 需注入 result stall、Vector stall、最后写 ACK stall、错误、abort 和重复 tag
  验证这些条件。当前 9 项纯整数测试**没有执行这些 RTL/协议压力测试**。

## 成本和完整 block 分母

Q/K 全形状工作量 352,321,536 FMA，86,016 个全宽 Matrix issues，229,376 个
输出。63 树加法为 14,450,688 个 FP32 Add，显式 tail +0 为 229,376 Add。

- partial snapshot 一次：58,720,256 B（56MiB），1,835,008 次单bank32B写
- 63 树节点，2R+1W：173,408,256 B；1,806,336 个读阶段和1,806,336次单bank写
- +0：1R+1W=1,835,008 B，零操作数立即数不另读 SRAM
- 最终根读取：917,504 B
- 两次独立 Q/K 激活输入：1,572,864 B（原 FP32 transport）；转换/本地写单列
- 权重按 M16 tile 重读：44,040,192 B（42MiB），无跨 8 个 M tiles 免费重用
- raw tensor 最终写/ACK：917,504 B
- Matrix 组、fill/drain、输入 SRAM 读、外部 request/ACK 全单列

`Costs` 全是可更改的正整数服务假设。默认外部单 64B 事务单列请求+ACK 2 单位，
不取 burst 或 overlap 优惠。此串行和只属于本候选的条件流程；旧硬件能否跑出
该延迟、哪个步骤能重叠，都没有证据。某些延迟若增加，账本必须随之增加。

Bias/RoPE 保持原 owner，单独列出可核算工作：Bias 229,376 Adds、2,752,512 B；
RoPE 458,752 Muls+229,376 Adds、2,752,512 B。具体转换次数和 service 延迟
由数学候选冻结的原节点/实际共享引擎决定，当前显式 null，不能当 0。

全 block 必须用：

`6,014,828,544 / (4096 * 完整 pc0..20 launch接受→terminal result接受的wall cycles)`。

其中包括原 Norm、V、Bias/RoPE、KV、QK/Softmax/PV、O、残差、FFN、Down、
所有转换、搬运、握手、idle、clock gate 和最终 ACK/drain。不能用 Q/K issues、
软件 ticks、CPU 秒数或仅忙周期做分母。这里只给条件式：

`Cfull = Cprojection_core + Cunchanged_bias_rope_conversion + Cother + Cinterowner`。

其他矩阵即使理想满载也至少 1,382,448 单位。仅在默认串行核心假设成立时，
加这个理想余量得到完整块比率上限约 13.4690%；这还故意忽略了 Bias/RoPE 等
正成本，所以是乐观条件上界，**绝非硬件性能目标/预测**。实际 cycles、hardware
utilization、完整 block cost、转换 service cost 全保持 null。

## 审查结论与验收条件

- P2：新 feeder/partial spill/共享树 route 未连接。后果：当前 RTL 不能执行
  这套图；定位 MatrixPipeline/StreamingDense/Elementwise loan 边界。接受条件：
  固定 4096MAC/5contexts/同 A/B SRAM 的 elaboration+资源表+完整事务仿真。
- P2：大量 spill/tree/weight reread；满 issue 几何不能证明 QoR。接受条件：
  固定时钟完整 block 实测、stall 分解、SRAM端口与综合/时序报告。
- P1（实现必须防止的风险，非声称现 RTL 已有缺陷）：slot/epoch/ACK 提前复用
  可能污染结果。接受条件：逐 slot 写提交证明和上述 stall/abort/tag 压测。
- 功能：这里只证明整数图依赖保持，浮点域/异常/signed-zero 留给独立数学测试。
- 协议：清理契约已列，尚未实现验证。
- 物理：总容量和每 phase 银行地址可容纳；新增路由/控制未综合。
- QoR：只有显式服务假设下账本；没有硬件通过或吞吐结论。

不存在把上述 blocker 豁免为“数值通过就算硬件通过”的条件。软件候选可以
继续独立证明数学，但 hardware/RTL/performance 字段必须保持未验/null。

运行：

`python -B -m unittest candidates.qwen2_qk_reduction_resource_candidate.test_screen -v`

`python -B -m candidates.qwen2_qk_reduction_resource_candidate.screen`

9 项 cold tests 检查固定源、精确左右树图、K 覆盖、合法 contexts、slot 生命周期
计划、银行地址/端口、完整 live-set、全块分母区别和 null 证据边界。
