# TEMP：五块128完整算子规模与当前路径上界（非DUT实测）

## 口径必须分开

1. 下表 `Matrix-useful` 为完整block各Dense和Attention矩形QK/PV的数学乘加数量；一乘加=一MAC，不是2FLOP。MoE N1共享门只计真实N1，排除31个零填充列。GDN/归一化/门控等在Vector或Scalar完成，不能作为4096 Matrix资源有效工作计入分子。
2. Attention当前源码枚举包括masked未来key；矩形计算工作量与因果有效语义分别列出。若最终指标只接受因果有效MAC，需减少分子，不能增加利用率。这里用较宽松矩形口径作上界。
3. 实际物理发射由acceptedSteps×512计数；固定容量分母始终4096×完整block周期。没有测得完整周期/硬件计数，因此不是实测利用率，也不宣称性能资格通过。
4. 下表是基于运行形状的操作清单，不是捕获硬件counter的结果；上界只限制当前执行映射/调度，不限制未来统一架构的可达性。

## 五块完整Matrix操作清单

|profile|四投影合计|Dense FFN|routed FFN|shared FFN|router|共享门N1|Attention矩形|总Matrix-useful|
|---|---:|---:|---:|---:|---:|---:|---:|---:|
|P0|704643072|5284823040|0|0|0|0|50331648|6039797760|
|P1|1346371584|1409286144|0|0|0|0|0|2755657728|
|P2|939524096|1409286144|0|0|0|0|67108864|2415919104|
|P3|4311744512|0|3221225472|402653184|67108864|262144|0|8002994176|
|P4|3489660928|0|3221225472|402653184|67108864|262144|134217728|7315128320|

复现 `full_block_bounds.py`。M=128，投影=M×H×(QKV总宽+Z或Qgate宽+AB宽+O输入宽)，Dense FFN=3MHF；MoE routed=1024×3×2048×512，shared=128×3×2048×512。

源依据：UnifiedRuntimeProfile.scala:81-121 给5种shape；HostBlockCommandsV4.scala:1317-1335 指定GDN三投影QKV/Z/AB和Attention gatedQ/K/V；1453-1470指定O；1530-1544指定小模型FFN；UnifiedMoeDenseWritebackV2.scala:25-44指定expert/shared矩阵；UnifiedMoeRouterDenseV2.scala:42给router；HostMoeSharedGatePlanV5.scala:35-36,69-74,104明确逻辑N1/物理N32。P0无Qgate，投影分别1536/256/256/O1536，H1536/F8960/head12/d128。

Attention因果语义MAC（QK和PV，前缀128、无历史）：P0 25,362,432；P2 33,816,576；P4 67,633,152。对应矩形 `2×128×128×heads×d`。Bf16CausalGqaRuntimeOwnerV14.scala:90-111 明确当前QK仅slice0、PV八slice、masked keys不跳过；QwenOwnerProtocol.scala:359,798用矩形计数。这里P0仍给宽松100%几何界，不声称已闭合其QK/PV调度损失。

## 当前完整block几何上界

令T为表中总量，W为专家M128映射与共享门N32的无效容量，Q为QK只用slice0导致的闲置7×QK容量，理想其余工作全满速：`U <= T/(T+W+Q)`。

- P0：仅可给宽松100%，不代表接近目标。
- P1：几何100%，但下面实际GDN串行路径远严于此。
- P2：≤91.13924%，尚未计softmax/访存/同步/格式化，不能当90%已达。
- P3：≤8.35477%，条件为原始Torch参考的226个active experts。
- P4：≤7.92108%，条件为原始Torch参考的218个active experts。

P3/P4硬件路由尚未数值验证，不能说实际DUT选择与参考相同；本审计没有馈入参考ID。仅映射改成M16仍是先前27–29%的专家局部界，不能据此说新架构已实现/可达90%。

## GDN execute phases5..17 的确定源级周期/流量下界

实际 GdnRuntimeChunkLeafCollection.scala:64-69实例化ExecuteV8；它不是Matrix引擎，而是当前 **16有效lane兼容接口** 使用共享32bank。用户优先32lane全链方向尚未因bank实现而自动落实。

GdnRuntimeChunkExecuteOwnerV8.scala:39-50列13个phase；133-139给每phase精确expectedReadBeats/expectedVectors；每输出写64B beat数按shape确定。Coordinator.scala:258-274使每个head的两块64token顺序执行各phase，valueHeads为P1=16/P3=32。读取、vector和写各有独立issue/wait FSM状态（52-53、106-124、190起），同状态机不可重叠、至多一个未决；故每事务至少2周期，严下界 `2×(读beats+写beats+vector请求)`。

|仅phases5..17|读beats|写beats|vector请求|串行握手周期下界|DDR请求字节|
|---|---:|---:|---:|---:|---:|
|P1,16heads×2chunks|11368448|237568|21102592|65417216|742785024|
|P3,32heads×2chunks|22736896|475136|42205184|130834432|1485570048|

每K读取B，A每16K读取；并非缓存驻留假设。不同phase之间/state/conv/rawprep/derived/pair/transpose/format等前后成本未全部加入，因此是保守下界，不是周期预测。QwenOwnerProtocol.scala:398,440-451,525-548,842的active/mode互斥禁止当前block的普通Dense与该chunk job重叠；Chunk完成才释放下一job。由此 `U <= T/(T+W+4096*C_execute)` 得P1≤**1.01796%**、P3≤**1.26692%**。只适用于当前固定调度及上述Matrix-useful口径，无端到端实测。

GDN数学上也有dot/triangular solve/state update的MAC等价工作，但当前它们由独立Mul/Add向量请求完成，不是Matrix物理MAC；因此不能为了抬升4096利用率把它们加进Matrix分子。另一个“全部模型MAC等价吞吐”指标可单列，不能混用。

## 100 GB/s显式条件，不假设时钟/目标内存

取100×10^9 bytes/s可持续有效带宽，只有上述execute流量的最短时间P1≥7.42785ms、P3≥14.85570ms；未含权重及其他流量。没有假设实际系统提供该带宽或某个时钟。

设时钟f Hz，带宽必要界 `U <= T*100e9/(4096*f*B_execute)`。即使忽略其他所有流量，要在此口径达80%，f必须≤P1 113.217MHz/P3 164.403MHz；90%必须≤100.637MHz/146.136MHz。**这不是推荐降频达标**：当前串行握手周期界与f无关，仍仅约1%，而且这些频率只是带宽约束的必要条件。真实cache/驻留变更可改变B，不能把当前反复DDR流量外推到未来设计。没有用营销GB/s或隐含1GHz作测量。

## 设计含义

固定4096保持不变。除了专家小M资源布局，GDN完整主链必须把当前重复DDR读、16lane兼容接口与单未决phase循环纳入：跨tile/phase缓存、独立head有序并行、32lane端到端credit/tag/retire和精确流水Div保留sqrt；是否把dot映射至Matrix还必须验证独立Mul/Add与FMA的舍入等价，不能直接替换。所有新统一硬件五块重测，不迁移旧PASS。
