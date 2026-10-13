# 已过样本的 MAC 与占空比证据

2026-10-13。首批盘点15个已有数值结果的窗口，覆盖Qwen2完整cold M128、0.8B L0完整M16/M128、L3完整M16与M128前缀，以及三个历史RTL revision的M1窗口（L0两个、L3一个）。重复实现/窗口分别记账，不把它们算成15种完整block。历史部分只有固定算术门通过的样本单列，不能升级官方模型验收。

[机器可读逐case记录](../reports/execution/PASSED_CASE_UTILIZATION_20261013.json)绑定各原始报告hash、执行身份、数值范围、资源与已有计数。它是现成证据后处理，不触发模型重放或RTL生成。当前正在执行的L3完整双M128不预填成功或性能数据。

本轮逐字节核验引用的12份receipt/source记录；L3完整M16的91源另逐项等于git43fc70f和当前文件。历史Qwen2/L0原commit对象不全在现环境，当前源已合法后继变更，因此其他旧结果沿用原封存receipt/hash和既有验收，不声称本轮重新核完其旧源码闭包，也没有为统计重抓取/重跑。

## 统一口径

- 一个MAC是一次乘加，不按两次FLOP记。固定Matrix为1个、8 slice×16行×32列，共4096 MAC/拍；闲置、屏蔽、时钟门控时间均不缩分母。
- 完整利用率=逻辑useful MAC / (4096×launch接受到最终terminal的完整硬件周期)。首末边界和计数器重置/差值必须说明。
- 发射占空比=接受wide issue的周期数 / 同一个完整区间。pipeline busy、active-lane占空比另列；不能把发射率、useful/executed比例或某一阶段busy率互相替代。
- 软件tick可能包含同步宿主算术；C++配方FMA次数、逻辑事件数、源约束上下界、可行cycle预测与实际RTL计数分开。宿主秒数不进硬件利用率分母。
- unknown/null表示证据未保留或尚未建立，不表示零。stall分类若重叠，需报告交集/并集或说明不可相加。

资源不能只写“1 Matrix+1 Vector+1 Scalar”套所有历史实现。新Qwen3.5 typed模型共享16-lane Add/Mul和单Scalar服务；相关策略尚未生产Chisel接线。旧Qwen2调度SiLU另保留16个BlockScalarFloat lane，源码见VectorSilu/OverlappedSilu。六条历史RTL窗口记录本轮仅沿用其原4096 Matrix计数分母；未逐revision重新审计物理Vector/Scalar层次，相关实例/lane数明确unknown并标historical_receipt_resource_budget_not_independently_reaudited，不能把当前源码资源复制过去。新功能/流水寄存器、队列、仲裁和bank端口的面积及时序代价仍需记账。

## 现有可报告结果

| 样本与数值范围 | 已有MAC/事件证据 | 完整MAC利用率 | 占空比证据 |
|---|---|---|---|
| Qwen2-1.5B L0 cold M128，38b943c，公开21命令软件模型，27已分配官方门过 | 软件终态useful 6,014,828,544；executed 6,801,063,936；shared Add16,384请求 | unknown，17,361,158是软件tick | busy/active lane/stall时间线unknown |
| 0.8B L0 cold/carried M16、M128，原完整typed软件已分配门过 | 原封存报告没有完整实际MAC计数；源码Dense逻辑MAC每窗M16为344,457,216，M128为2,755,657,728 | unknown；源码推导不能补作实测 | unknown；54,840,934仅M128双窗软件tick |
| 0.8B L3 cold/carried M16，43fc70f，56已物化producer及最终output/KV/行和过 | C++ FMA调用2,350,383,104／2,350,907,392，含填充；basic Scalar772,864／779,008 | 硬件unknown；单Scalar条件上界≤3.102574%／≤3.089058% | 真实busy/active lane时间线unknown |
| 0.8B L3 cold/carried M128，C2八阶段前缀 | 每窗671,088,640软件FMA，1,210,434软件tick；22/57加4个前缀输出门过 | unknown；不是完整block | unknown |
| 0.8B L0双M1，d7ce9bd与79bbe75两历史RTL实现，原native门过 | 每窗DUT useful Dense核对21,528,576，缺executed/周期端点 | unknown | unknown |
| 0.8B L3双M1，98c7d80历史RTL，仅frozen-recipe过、native仍open | cold useful18,354,176／executed294,682,624／3,106,174拍；carry18,358,272／294,715,392／3,109,624拍 | 实测0.1442611%／0.1441332% | accepted-wide-issue率2.3738528%／2.3714764%；pipeline busy仍unknown |

L3完整M16夹具position为0..15与128..143，实际KV长度16→32；不是连续position的32-token样本。使用冻结官方捕获的BF16 cos/sin常数，独立trig生成未验证。完整M128夹具为0..127接128..255。M16 Dense物理配方按128行映射，2,348,810,240 FMA/窗相对293,601,280逻辑Dense MAC有8倍填充工作；这一算术工作效率也不是占空比。

L3 M16条件界严格使用3N−1：假设每笔记录的基本Scalar请求一一映射到同一个未改动BlockScalarFloat、无融合/向量化/复制，idle→normal→done最快II≥3。端点约定为第一请求接受沿之前至最终结果首次可用，计入接受沿；单请求至少计2个区间，相邻接受至少隔3拍。完整窗口下界2,318,591／2,337,023拍，仅由该资源算出的Matrix上界如表。矩形QK/PV分子仍包含因果零系数位置，且忽略Div/Exp/Sqrt/访存，故只是乐观约束；不能宣称所有架构都受此上限。

历史98c7 RTL使用每请求1–7拍伪随机DDR延迟及末ACK额外53拍，是协议压力环境，不是真实DDR系统性能。wide_steps为73,736／73,744；pipeline stall每窗24,960个事件有记录，仍缺互斥原因/跨引擎重叠时间线。每个指标都保留原source/RTL/ELF/输入身份范围，不能把它迁移给当前M128软件映射。

## 流水工作的实际优先项

1. 当前完整typed协调器在整owner成功退休后才切下一owner。先用真实依赖和不重叠bank区域，检查可否在已ACK的独立tile上重叠后续运算、当前结果排空和下一tile供数。需要准确bank 1R1W、workspace lease、read/return tag及全部结果credit；错误时在飞排空，最终双root generation仍原子提交。
2. 单Scalar逐请求握手让Matrix在RMS/Norm/softmax等长阶段空闲。仅加队列不能降低现有II；独立head/row调度、复用既有Vector lane或流水化单元均须保持FP32归约次序/舍入、端口与异常策略，显式预算pipeline寄存器和控制。L0现有Vector-only chunk映射即使每拍一个issue，其M128条件上界仍约3.16764%；单靠调度流水不能消除此资源工作量。
3. 原Dense已有K16双权重缓冲，不能把既有重叠重复当改进。下一次需先量化供数、结果credit/反馈与写回等待，再在现有五个累加上下文和共享bank容量中验证burst/预取/排空重叠。M1几何填充上限单列，固定4096分母不变。

这三项是有明确资源前提的整改方向，尚非已实现性能提升。本轮优先完成冻结L3 M128数值；不在该运行中改源或插入新观测。

## 后续每case必须补齐的观测

下一次与实际数值运行绑定的计数器小增量，应逐样本封存：完整launch/首次terminal端点、useful/executed MAC差值、Matrix wide/slice issue及busy并集、Vector/Scalar opcode接受/返回/活跃lane周期、真实DMA读/写ACK、供数/依赖/写回/调度等待、跨tile/引擎重叠与每类计数的重置/饱和语义。先小例证明计数器无扰输出、握手、故障/复位和终态发布，再合并完整模型/RTL验真；不能仅为补丢失历史统计重跑昂贵旧case。

todo：Qwen2新共享Add/bank开销的完整cycle模型校准、L0实际MAC全量计数、L3新完整M128终态统计、所有当前软件映射的硬件busy/完整周期。U01和五block数值/性能联合总门继续open，未承诺80%或90%。
