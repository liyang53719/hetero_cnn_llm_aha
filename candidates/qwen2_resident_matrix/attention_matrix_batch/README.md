# 固定 Matrix 资源的 Attention batch 行为候选

## 中文计划
- 已完成：与原始 OfficialAttentionOwner PV16 生成器的 M1/M2 和 causal 15/16/17 边界逐位比较；19项冷测试 normal/-O通过（2.785/2.881秒），使用python -S -B无site packages。10个原始源码与6个候选文件冻结及资源结构检查通过。
- 已完成：有限selected-cell准备范围及scalar源约束修订的独立审查；最终19项 normal/-O通过（作者2.715/2.619秒，审查2.719/2.606秒）。
- 已实现：QK 同 query/head 的最多16个 keys；PV 同 query/KV-head 的六个 GQA heads。无新 owner/top、MAC、operand bank 或 per-row freeze。
- 待完成：实际原始 Matrix profile/controller 接线、共享 ALU/exp/div 与 bank/DDR 完整调度、父级生命周期 RTL 单元验证。当前没有新 RTL 或完整数值运行。

## 精确算术范围
QK 的 A[r]=Q[16*step+r]，B[16*k+r]=K[k,16*step+r]，使用 cell[r,16*k+r]。保持八个 FP32 FMA depth 更新、按 r=0..15 的16次 FP32 add、完成 dot 的 BF16、FP32 multiply 0x3db504f3、score BF16。PV 把同 token 的六个 heads 放 rows0..5，使用128 columns；原始 FP32(probability*inverse) 后 Matrix ingress BF16、key 递增的 FP32 FMA、最后 output BF16。相同规范化数值可广播，但其计算次数单独统计，不假定免费并行标量操作。

不把16个不同 causal query 的未来 key 填零；它们的结束点不同，额外零 FMA 会改变 signed-zero/非有限语义。非有限 selected lane 仍由逐步检查拒绝；该检查在此是算术 oracle，emit-last 的实际控制器错误报告/接受债务时序尚未实现。

model.py 使用一个4096-cell host accumulator 的 selected-cell dependency projection；不执行无关 cells 的数值计算，另计所有启用物理 cells 的 issued FMA 数量。它证明被选输出的算术映射，不证明完整 native Matrix 或 RTL。结果/输入 Python objects 是测试材料，不是新硬件 payload storage。两个 callbacks 必须提供精确 FP32/RNE、BF16 语义；测试独立驱动原始生成器。

## 资源和时序边界
现有 MatrixPipelineService 有8个并行32-column slices、5个 accumulator contexts、8个 metadata slots、2个16KiB result tiles。所有启用 slices 合并成一个 wide result，不能把8/4 slices误算为8/4独立返回。保守调度模型只占1 context、1 metadata、1 result tile；hold直到ACK，之后 completion/done 才退休。latency 为明确的假设参数，并非测得 RTL latency；完整跨context高吞吐安排仍未实现。

M128：legacy QK+PV 1,585,152 steps；packed QK55,296，PV16,512，共71,808个wide steps，对应508,416个512-MAC physical slice issues（260,308,992次issued FMA）。QK causal pairs99,072仍需1,585,152次有依赖的 scalar fold add。

原 BlockScalarFloat 请求只在idle接受（BlockFloat.scala:55,58），normal计算转done（71–81），done消费后才回idle（108），因此即使新decoupled client也至少每3cycles一次add。默认bound按此3-cycle最小间隔：fold>=4,755,456cycles，加Dense1,462,272和packedMatrix71,808，共>=6,289,536cycles，完整block useful MAC6,014,828,544 /4096 /该下限 <=23.35%。这是仍忽略exp/div/feed/DDR的上界，非实际性能。

当前Qwen2Block calc→scalarReq→scalarRsp→attReduceDone→attReduce路径（252,284–285,471–472）普通fold约5cycles/add；模型可明确传入5。1cycle/add只保留为标记hypothetical_unrealizable_ii1=true的不可实现数学理想：3,119,232cycles、47.08%。95.7228%只是连scalar都不计的issue-only ceiling。现有Dense/Attention单owner/mode尚不能重叠；复用其它既有16ALUs也仅是未来需接线/调度验证的方向，不计入当前结果。

不能把软件执行时间、selected-cell测试、issue上界称为硬件 utilization。80%/90% acceptance固定为false。共享 ALU latency/II、exp/div、operand BF16 materialization、bank feed、KV DDR、result stalls、合法 Dense/Attention overlap均待完整计入。尤其 packed operand feed不能凭Python同时访问多个 key就假定bank单周期供给。

存储放置/bank容量与供给带宽、abort/reset/accepted-debt协议均未实现。host输入/概率tuples与projection数组不能作为借用bank映射成立的证据。当前严格逐位等价范围为有限算术；非有限逐步拒绝仅是oracle防护，不能冒充final-only硬件相同错误时序。source checker同时冻结原源码并断言5contexts/8metadata/2result tiles及8leaf/singlejoinedresult结构。

GroupSchedule.held只含index/mask/last元数据，不承载16KiB payload。backpressure测试仅证明这些元数据保持和done fence，不能声称实际数据经过stall保持。真正payload/port/debt验证仍待既有parent与Matrix单元接线。

M128仅完成全部128个causal长度的packing/count枚举，不是M128数值执行。独立Fraction oracle在M1/M2与边界用例已经进行真实FMA/标量节点运算；完整M128约25.36M useful FMA的纯Python精确比较不属于本次短测试，后续需单独审查有界数值runner。

精确复现命令（namespace packages，不使用generic unittest discovery）：

    python3 -S -B -m unittest candidates.qwen2_resident_matrix.attention_matrix_batch.test_model candidates.qwen2_resident_matrix.attention_matrix_batch.test_schedule -q
    python3 -S -B -O -m unittest candidates.qwen2_resident_matrix.attention_matrix_batch.test_model candidates.qwen2_resident_matrix.attention_matrix_batch.test_schedule -q
    python3 -S -B -m candidates.qwen2_resident_matrix.attention_matrix_batch.check_sources
