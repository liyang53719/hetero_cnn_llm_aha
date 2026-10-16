# M128 Attention 固定资源调度审计（2026-10-16）

## 结论和适用范围

现有控制不能把 QK fold 与 Dense 重叠。即使给予不可能的完全重叠，现有单 Scalar 的 fold 吞吐也将整块有效 MAC 利用率上限压到 **30.88%**。现有 16 个 Vector ALU 的按 key 并行 fold 是最小有价值的改动，但单独不足以证明 80%，更不能证明 90%。必须同时解决 Softmax、原始 KV bank 供数、整个 FFN SiLU 的实际资源占用。

本目录只增加可复算的必要条件、源码证据和设计建议；没有优化 RTL、数值验收、运行时测量或 CI/综合结果。所有百分比均为省略费用后的上限。`source_pins.json` 固定所读源码 SHA256；源码或本目录程序改变则检查失败。

路径缩写：`C = chisel/continuous_prefill/src/main/scala/heteronpu/continuous/`；其余路径均相对仓库根目录。

## 1. 吞吐预算

M=128，Q heads=12，headDim=128，固定分母=4096 MAC/cycle。

- causal pair 数 P = 12×128×129/2 = 99,072。
- 16-key QK packet 数 G = 12×Σ(n=1..128)ceil(n/16) = 6,912。
- QK issue = 8G = 55,296；六头 PV issue = 128×129 = 16,512。
- Dense issue = 1,462,272；总 Matrix issue 下限 B = 1,534,080。
- 整块 useful MAC = 6,014,828,544；理想 useful cycles = 1,468,464。
- 80% 要求总周期 ≤1,835,580，因此除 B 外只有 **301,500** 周期。
- 90% 要求总周期 ≤4,894,880/3，因此除 B 外只有 **292,640/3 ≈97,546.67** 周期。

Dense/useful 取自 `reports/execution/QWEN2_DENSE_BLOCK_REDUCTION_20261012/M128_RESULT.json:239,1561`。该报告明确 `hardware_cycles=null`，不能把 issue 当作 Dense 实测 wall cycles。

## 2. Scalar 实际 II，不是 Python 调用数

`C/BlockFloat.scala:48–55,58–81,108`：一个 `HeteroFP32Alu`、一个 divider；`request.ready := state===idle`；Add/Mul 经 `normal` 进入 `done`，结果握手才返回 idle。

无反压最早时序：edge0 接收，edge1 计算，edge2 结果握手，edge3 才接收下一项。**Add/Mul 最小 II=3**。`C/Qwen2Block.scala:252,284–285,471–472` 的 `attReduce → scalarReq → scalarRsp → attReduceDone` 另有控制开销，普通相邻 fold Add 的请求间隔为 5。

每个 score 的 16 条 stripe 必须保持原顺序：`official_bf16/owners.py:133–139`（目录前缀 `candidates/qwen2_resident_matrix/`）。只允许不同 score 并行，不允许树形归约、FMA 替代 Add、改变 BF16 完整 dot/scale 边界。

- fold =16P=1,585,152 Add。
- 即使重写客户端，服务下限 =3×16P=4,755,456 cycles。
- 串行 B+fold ≥6,289,536，利用率 ≤23.35%。
- 原 FSM 的普通 fold 路径下限 B+5×16P=9,459,840，≤15.53%。
- 给予完全重叠也需 ≥max(B,4,755,456)，≤30.88%。
- 1 Add/cycle 的 47.08% 只是不可直接实现的算术理想，不能标为当前 RTL 预测。

`C/BlockFloat.scala:90–98` 的完整 ExpNegative 为 request、scale、floor、fraction、7×(mul,add)、finish、done，共20个最小请求间隔；|x|≥80 分支为3。Div/Sqrt 等待真实 `inReady/outValid`（:83–89），本审计不假定固定 divider 延迟。

## 3. 现有 owner / context 不允许跨任务免费重叠

- `C/QwenOwnerProtocol.scala:147–153,328–342,366–380`：单 `active/mode`；done 后才释放；memory/response/Matrix 按模式选择。
- `C/Qwen2Block.scala:98–113`：外借 Scalar 只在 core idle；Attention 内部仍是单 FSM。
- `C/MatrixPipeline.scala:16,25–30,49–69,112–135`：**5 accumulator contexts、8 metadata、2×16KiB joined results**，不是5个独立 owner。group 只在 idle 接收，done 等待 result FIFO 清空；closed context 不能在同一 group 清除重用。
- `rtl/matrix/candidates/rev8b_b/bf16_context_scheduler5_rev8b_b_candidate.sv:29–38`：同 context 的前一步必须 completion，不能只按平均 II 越过依赖。
- Dense partial→sum 当前也明确互斥：`dense_block_reduce/DenseBlockReductionCoordinator.scala:74–75,103–105,161–165` 等待 Matrix/DMA/window/drain 退休后才授予 sum/vector；不是已经支持 Dense/fold 交叠的接口。

## 4. 16 个现成 ALU 能做什么，不能做什么

`C/Qwen2Block.scala:128–130` 已有16个 `HeteroFP32Alu`。最小 fold 改动可每 lane 对应一个 key，每 cycle 做同一 stripe 的 Add，stripe 从0走到15，使用现有 accumulator/临时寄存器；不同 key 独立，同一 key 的位序与舍入不变。

- 每 packet 16 fold cycles，尾 packet 无效 lane 不作为有效结果，因此总下限16G=110,592。
- 串行 B+16G=1,644,672，≤89.29%；再加每 packet 一次向量 scale 为1,651,584，≤88.91%。
- 不能把 `ceil(P/16)` 代替 G 偷掉每 query/head 的尾包；若跨行重新打包，必须增加实际 context/identity/storage 调度证据。
- 当前 vector 只接回 `out`，未接 primitive flags。复用须保留 Scalar 的 underflow/invalid/overflow/nonfinite 拒绝规则（`BlockFloat.scala:74–80`）、BF16 溢出检查、stable held result、abort/debt。
- Vector 也服务 Norm/RoPE/Bias（`Qwen2Block.scala:317–328,456–461,512–515`）。授予 Attention 时不得同时记这些工作完成。

更适合先做**同一个 Attention owner 内**：最多5个独立 QK packet 的 Matrix contexts；现有2个 result slot 中一个保持供 fold，另一个允许返回；仅在16个 stripe/scale 消费完成后 ACK。其他合法 context 的 Matrix steps 可与 fold 交叠。依赖和 FIFO 反压决定真正重叠量，不能直接用 max(总算术计数)当 wall cycles。新 group 仍受 done/drain 限制。

## 5. Softmax 和 SiLU 是尚未隐藏的算术债务

`C/Qwen2Block.scala:475–484`、`official_bf16/owners.py:144–155`：每 pair 需要 subtract、ExpNegative、按 key 顺序累加；每 query/head 还需要 reciprocal；PV 需要 probability×inverse。

- 当前 Scalar 上 subtract+sum 已需2P×3=**594,432**，大于80%的全部301,500 overhead。
- 每个非空有限 row 至少存在一个 max，因此至少1536个 exp(0)走完整路径。exp+subtract+sum 的数据无关下限为 `9P+17×1536=917,760`，尚无 scale/div/PV normalize。
- 把六个 GQA heads 的 ordered sum 并行才不改变每个 head 的相加顺序；不能把同一 head 的 key sum 换成16路树。
- `C/VectorSilu.scala:21–34,43–65,94` 已存在16个 `BlockScalarFloat`，可作为后续受控借用的资源依据；不是新增16个 SFU。当前只执行固定 SiLU 六阶段，不能直接拿来当任意 Exp 向量端口。
- `ffn_tiles/tile_ports.patch:16–24,58–62` 和 `dense_block_reduce/vector_add.patch:46–61,90–127` 是已有候选 loan 的参考：现有接口只增加 BinaryAdd，并保持外借时排他、失败排空；需单独扩充 Exp/Div/primitive opcode 和原数值策略。
- 整块 SiLU 有128×8960/16=71,680个向量。即使所有 Exp 都走 cutoff 且把 division 当零费用，exp+add+3mul 的现有服务占用已≥15×71,680=**1,075,200**；全部完整 Exp 时≥32×71,680=**2,293,760**。这些是条件下界，不推断真实分支比例。还没加入 divider、向量 wrapper、load/store、ACK。

因此“Attention 达到某 issue 吞吐”不能推导整块80/90。必须把原 FFN SiLU、Norm/RoPE 和 Dense reduction 也纳入同一固定资源时间表。

## 6. KV 银行冲突与供数

`candidates/qwen2_attention_resident_candidate/scratch.py:58–60` 原始 FP32 line 映射：bank pair=`2×(line mod8)`；`:100–126` 是 one-outstanding + held response/consume ACK。

K line=`16×key +8×kvHead +stripe`。同一 stripe 的16个 key 全在同一 bank pair；其16-key B vector 至少需要16次 bank-line 服务，不能声称一拍读取。无跨头重用，QK 总计8P=**792,576**个64B line read；理想六头完全重用时仍需132,096个读取，重用需要真实存储与调度。

`C/StreamingDense.scala:123–127` 每次 issue 读取全部 A/W banks；候选 transposed owner 的同步 port 在 `transposed_owner/TransposedDenseOwner.scala:103–127`，同样没有第二套 A 读端口。scratch 的 lease（:63–84）禁止第二 owner。容量有空闲不代表端口有空闲。

一个可审查、尚未实现的固定容量方案：保持原始 FP32 bytes，修改物理 KV 置换为 `pair=(key+stripe)%8; word=(key//8)*16+kvHead*8+stripe`。K占每bank256 words，V偏移256，总512≤1376，保持16-bank总容量不变。16-key同stripe在每pair最多2条，可用两轮全bank读组装 B，但必须实际增加**多line请求/响应控制、读端口 mux、BF16 转换和中间寄存器借用**；不能继续用旧单line API宣称两拍完成。`constraints.py` 只检验该置换的双射/冲突数，不证明电路连接、时序或吞吐。

可以借用 core 的 `denseWeights` 256×32b staging（`Qwen2Block.scala:121`）组装256个BF16 B operands；具体 live-range/类型需新设计审核。不能把软件 list 充作硬件缓存。保持一整块16-key×128的 BF16 K panel则是4KiB，必须指定已有 buffer 及排他租约，不能凭空增加。

## 7. 实际独立工作与下一道门

数学独立性：1536个 query/head row、6912个 QK packets；同一 row 的不同 key 独立，六 GQA heads 共享 K/V；每 row 的 Softmax 等全部 scores/max，PV 等该 row 的 sum/inverse，O Dense 的一行等其12个 heads 完成。保持每个 dot 的8-step FMA和16-stripe Add顺序，PV保持逐key顺序。

现有 scores/probs 各只有一个 `maxTokens` 深度的单word SRAM（`Qwen2Block.scala:126–127`）；六头 PV 同时工作需要6个 probability rows。必须复用并明确租用现有 local fabric/tile storage、列明 bank/port，否则不能把 Python 的6条数组视作已实现。

整个 Dense 不是可任意隐藏的背景工作：原 public21 的 Q/K/V→Attention→O→Residual/Norm→Gate/Up→SiLU→Down 顺序见 `official_bf16/execution.py:31–46,75–79`。整块 O/FFN 依赖 Attention；只有重新审查内部 row/tile wavefront 并保持对外 publication/ACK/event语义，才有跨 row 的重叠。V projection 数学上不依赖 QK，但现行 KvAppend/Attention事件及同一 Matrix/A lease不允许把其12,288个 ideal Matrix cycles自动记为隐藏。仅凭5 contexts不能改变这些依赖。

建议下一最小实现门：**一个受资源约束的 Attention tile postprocess 控制模型**，暂不改 public Host或宣称80/90：

1. 复用现有16个 Vector ALU，按 key 并行、有序 fold/scale；显式5-context、8-metadata、2-result credit；每cycle最多真实可用端口数。
2. 原始布局与候选 swizzle 两条 feed 模式并列；每个 accepted bank read 计费。记录本周期 Matrix、vector、Scalar、bank占用和stall原因。
3. ExpNegative 若借现有 SiLU16 cores，先补真实受限 loan opcodes及逐lane latency/branch/flags；ordered sum按独立head并行。原 Scalar 路径必须保留作反例。
4. 六头 score/prob/Q与暂存明确映射现有 storage，证明无双owner、无新增payload容量；负例覆盖held result、错context/tag、bank冲突、abort以及credit耗尽。
5. 先用M1/M2/M16/M128解析计数和轻量事件模型验必要条件，保持BF16边界/带符号零/溢出精确比较；再审查完整FFN/attention联合时间表。只有实际RTL wallcycles包含全部stall且≤阈值，才关闭80/90门。

若固定现有 SFU/port 的必要条件仍不满足，就应提交资源变更提案和新分母/面积账本，而不是把未来并行运算记为免费。当前无足够证据承诺固定资源方案已经能达到80或90。

## 复现（无外部包、无 native/RTL）

`python -S -B -m unittest candidates.qwen2_resident_matrix.attention_resource_audit.test_constraints`

`python -O -S -B -m unittest candidates.qwen2_resident_matrix.attention_resource_audit.test_constraints`

`python -S -B candidates/qwen2_resident_matrix/attention_resource_audit/constraints.py`
