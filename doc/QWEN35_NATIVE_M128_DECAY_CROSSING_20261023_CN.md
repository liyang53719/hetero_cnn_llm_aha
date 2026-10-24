# 单 head 原生 M128 累积衰减跨 80：软件 staging 通过

## 本批结论与范围

2026-10-23，基于 `ee15adc016e83b00e628445507da97d7e579638f`，新增一个显式 opt-in
测试，真实执行原 InputPrepOwner 的 128 token，再接原 ChunkOwner 的两个连续 chunk64。
不是两个 M1，也不是循环单 token recurrence；没有替换 `_compute`、`_op`、`_mul_add`、
Scalar evaluator、native 函数或原控制/事务方法，没有把参考矩阵写入实际 owner 内存。

本批只确认 cold、单 head、dk=dv=128、合成 raw 边界输入下的 native 软件 staging。
不是 all-head、FullBlockCoordinator 完整数值、官方权重/PyTorch、Chisel/HardFloat/RTL
或硬件利用率验收。生产代码、legacy exp/fatal30 默认和旧测试/收据均未改动。

源码：
- `candidates/qwen35_chunk_strict_contraction/test_native_m128_decay_crossing.py`
- `candidates/qwen35_chunk_strict_contraction/decay_crossing_reference.py`

## 真实输入、资源与算术

每个 chunk 的 row r 使用 raw Q=K=e[r]；chunk0 的 V=e[r]，chunk1 的 V 全零。
A_log、dt_bias、B 均为零；每个 chunk 的 A[1]=40、A[2]=41，其他 62 行 A=-8。
这些是合成 Conv/AB 边界，不是执行过 convolution 的输出。原 Prep 进行归一化、Q 缩放、
Softplus、g/beta 和完整格式写回；每个独立 g 都在 (-80,0]，g[1]=-40、g[2]=-41。
累积和从 row2 首次越过 -80，因此检查的是累计/差分衰减，而非非法单 token g。

Prep 和 Chunk 共用同一个 exact DecayScalar，两个 enable 标志明确为 True。
ChunkJob 与 ChunkOwner 同时显式选择 EQUAL_HEADS_EXPERIMENTAL_EXP；已有 R2 Vector16
使用 IEEE fatal mask 28、host_batch=True。保留 row1_streaming、原 ascending cumsum、
按 K 递增的 FP32 独立 Mul 后 Add 和每步 RNE，没有 FMA、Matrix 算术或算术旁路。

## 三类证据分别记录

1. 配方与存储边界一致性：
   - Prep 的 819200 个 FP32 格式 words 对照已有独立 Fraction/RNE 近似配方，其中
     49408 为活动 head0 字段，769792 为其他 head/格式零填充。
   - 新参考以字面量 P7 常数、Fraction 和整数 RNE 逐节点计算 split-ln2 配方；cumsum
     和差分也用独立 Fraction Add，不调用候选 evaluator。其余矩阵使用 NumPy 全平面
     按 K 递增、分离 Mul/Add 参考。48 个 scratch 矩阵共 403456 FP32 words 全部相同。
   - 完整 16384 BF16 输出 words 和 16384 最终 state FP32 words 相同。BF16 参考用
     保留位/余数规则，不使用 owner 的偏置公式。不是全部 21172544 个算术中间值比较。

2. 数学 exp 诊断，不设新的数值门：
   - 独立推导和实际统计均为 4418 次 exp，其中 252 个输入的绝对值至少为 80：
     cumulative 124、remaining 2、pairwise 124、chunk total 2。
   - 实际候选零输出、非正常数输出和旧 abs>=80 饱和均为 0。所有 exp 输出都为正常数，
     所以本批不覆盖 Scalar 的 subnormal-output 分支；不能借 native Vector 的真实 UF
     冒充已验证该 Scalar 分支。
   - 190 个不同的合成派生输入分别用 Decimal.exp 的 100/180 位和整数 FP32 RNE 诊断，
     两精度结果一致。观察到最大误差 1 ULP，180 个不同输入逐词相同、10 个相差 1 ULP；
     按 4418 次调用加权为 4296 次相同、122 次相差 1 ULP。阈值与 numerical_acceptance
     仍为 null。精度稳定不是区间证明，也不宣称全域正确舍入或官方模型数值通过。
     此处比较的是独立 P7 配方 words 与 Decimal 参考，没有直接捕获全部 4418 次实际
     Scalar exp 返回；stage words 相同与来源/计数核验不等于逐次 exp 返回 trace。
   - legacy 独立反事实参考使 chunk1 对角 rows2..63 的 62 个输出为零；候选这些仅来自
     carry 的输出保持正值，并在最终 BF16 舍入后仍非零。这不是实际执行 legacy owner，
     不证明旧 fatal30 能跑完本夹具。两参考的 chunk1 FP32 输出有 64 words 不同，最终
     state 有 62 words 不同。

3. native 操作、异常与真实调度：
   - 实际 654336 次 Mul→Add batch、18752 次 single；逻辑 Mul 662528 / Add 664896，
     lane 操作 Mul 10600448 / Add 10572096。这些是软件操作数，不是硬件周期。
   - 聚合 flags=0/1/3 的逻辑 issue 数分别为 1326214 / 1206 / 4。4 是 issue 数，
     不能解释为四个 lane 或已独立定位/核验全部下溢。
   - 选定 chunk1 state_decay row0/col0，在真实读取 chunk0 next_state 首 beat 的响应后，
     原 generator 恰好执行一个 native Mul 并停在生成的 WRITE。直接读取原 native
     输入/输出/flags 缓冲，独立 Fraction/RNE 验证该 16-lane issue：lane0 的正非零
     精确乘积舍入为 +0 且 flags=UF|NX=3，其余 15 lane flags=0。未改算术或 native
     绑定，未从 MulAdd 最后缓冲反推全部 Mul flags；这不是完整 flags oracle。

## ACK、carry 和 staging 生命周期

真实接受 724160 个 read、27776 个 write 及全部 ACK，751936 个 memory responses。
chunk1 从 chunk0 next_state 读取 132096 beat；最终 state staging 读取 1024 beat。
输出 32768B 与 state 65536B 合计 98304B 全部 ACK。两个 chunk 均完成，成功 staging
回执只退休一次。

每个 chunk 的最后 output ACK、最终 state ACK 和 held terminal 都实际施加背压，核验
不抢跑、不提前释放 Scalar/Vector、不提前完成。Prep 中间输出先真实发布；但 Chunk 的
scratch/output/state 均保持未发布，history/state commit 与 generation 不推进。

## 执行预算与身份边界

根执行一次：1 测试、0 skip/failure/error、exit0；unittest 35.920 秒，payload
36.064592641 秒，peak RSS 70340 KiB。1 CPU、512 MiB 地址空间、110 秒 CPU、115 秒
alarm、外层 GNU timeout 120 秒及 TERM 后 2 秒 KILL。复用已有 receipt 绑定 ELF，无
编译/下载/Torch/权重或长跑。只放行原 Prep 来源验证所需的两次同一固定只读 git show，
每次保留原 10 秒 timeout；其余请求的子进程/网络由本 runner 的 Python audit 限制。
这不是 owned-process-group supervisor 已运行或任意 native 沙箱的证明。

身份验证必须分清三层，不能统称完整 pre/post 依赖闭包：

- 1688 项 manifest 执行前后 hash 一致，主要是 candidate 文件，以及选择的 runner、
  native ELF/receipt、git/compiler 等证据。公开摘要列出其中相关相对 source pins。
- 原 Chunk source_identity 在 admission/terminal 另行核验 BlockFloat.scala、
  EmitHeteroFP32Alu.scala、ElementwiseMemoryEngine.scala 和上游 modeling_qwen3_5.py。
  这四项不在 1688 项 manifest 中。原 Prep 的两次 git show 校验的是 committed HEAD
  中的 GdnInputPrepOwner.scala blob，不把工作树文件冒充该 committed blob。
- 使用明确的解释器路径启动，但解释器不在该 1688 项 pre/post manifest 内。
  其 SHA256 `fa67443527ed9647f760d807e2a38f26340757123e643c4639cf273ed15d5ea7`
  于 2026-10-23 15:52:50 UTC 在运行后核验，只是 post-run 证据，不能追称 pre/post
  interpreter pin。也没有完整 Python/NumPy/native 依赖闭包或敌对解释器保证。

复现需重新审查来源、解释器、已有 R2 ELF/receipt 和有界 runner，不可裸跑后补封来源。
显式 opt-in 为 GDN_RUN_NATIVE_M128_DECAY_CROSSING=1，并必须给出经过验证的
GDN_VECTOR16_FINITE_MUL_UF_LIBRARY；启用后缺失/不符的库是错误，不跳过或自动编译。
本次原 pins、runner、result、log 及所有历史收据保持不变，只公开安全摘要与 artifact hash。

公开摘要：`reports/execution/QWEN35_NATIVE_M128_DECAY_CROSSING_20261023/summary.json`。
不公开私有绝对路径、原始数组、raw log 或权重。

## 中文计划清单

- done：单 head 合成 M128 的真实 producer → 双 chunk64 native 跨 80 软件 staging；
  独立配方/数学诊断分列；实际 carry、最终 BF16 信号、选定 UF 及 ACK 生命周期核验。
- ongoing：明确完整官方输入的数值与异常策略验收；审查全 head、完整 block 的真实
  中间值/资源/调度与 joint publication，而非从单 head 测试自动扩大资格。
- todo：保留现有硬件资源约束下的 Chisel opcode/FSM/异常策略绑定、完整 RTL 同刺激
  运行与最终完整周期/利用率验收；本批没有新的硬件周期或 MAC 利用率实测。

五完整 RTL 仍为 0/5，旧 Qwen2 M128 终态仍 UNKNOWN，不重启、不追认丢失的 PASS。
完整 block/官方数值仍未通过，最终完整 RTL 与 80%/90% 目标不变。尚未提交或发布；
公开只包含本批源码、文档和安全摘要，所有旧私有 pins/失败收据保持不变。
