# 接受后运算、实际数据保持的 M1/M2 Attention 候选

## 中文计划

- 已完成：新的 Matrix/Scalar 数值端口及原顺序 controller，首轮 M1/M2 scores/output 全word与原 OfficialAttentionOwner AST执行结果一致。
- 已完成：19项错误/ACK/反压及原owner数值对照测试 normal/-O通过（作者1.066/1.122秒，独立审查0.996/1.153秒）；28源+6本目录文件身份检查通过，独立审查完成。
- 进行中：下一存储门规划；当前Matrix result在fold前ACK，因此host tuple仍未物理放置，后续需改为消费期间保持原result FIFO所有权。
- 待做：真实 bank/register 存储布局与带宽、原端口 mux/flags、完整 M128、完整块联合调度、RTL验证。当前没有80/90%验收。

这是前两份 preparation 的下一步：每项浮点 callback 由已接受的工作触发，结果实际保存为word tuple并保持到matching ACK。不是先跑数值，再给trace附加周期。仅支持 M1/M2 synthetic Attention；没有启动完整Public、native、编译器或RTL。

## 源算法与物理资源边界

QK：8步16-stripe FP32 FMA，按key映射cell[stripe,16*key+stripe]；每score原序16次Add、BF16 dot、乘0x3db504f3、BF16score。PV：同一token/KVhead的6个head共享causal末key，128列、key升序；概率FP32归一化，Matrix入口一次BF16，最后输出一次BF16。未加入未来key的零FMA。

Scalar端口依赖已发表 attention_scalar_schedule；Vector/SiLU pools来自原16ALU与16core，但它们的通用借用mux尚未实现。全局最多一个Matrix或Scalar phase，当前不重叠Dense/Attention、两个资源池或Matrix/Scalar。每个Scalar phase有真实元数据lease/accepted debt/held ACK；controller在整份job期间禁止ordinary owner admission，任何数值失败保持禁止。

Matrix端口只有1context/1accepted step/1held joined tile，4096个逻辑cell，其中只计算dependency-selected cell。其余4contexts、7metadata slots、1result slot不用；不模拟未选cell运算及其异常。FP32输入在接受后的return事件做BF16转换，然后选中FMA执行。一次result ACK退休联合tile；不是按slice分别ACK。early/foreign ACK不退休。

原完整4096cell物理数据通路和未选cell fault aggregation尚未证明等价。因此PASS范围是有限selected-cell数值及提出的握手行为；不是全Matrix后端异常等价。Matrix abort终止未接受step、排空已接受step并发出poisoned terminal，需要后续硬件控制审查。

## 真正计费的事件与明确假设

`Timing`必须显式传Matrix latency、divider spacing、feed stall、result stall。它们不是测量；所有周期字段叫hypothetical_ticks。原Add/Mul最小spacing3；Vector假设capture/ACK spacing2，包装层还要等实际payload capture后才允许ACK。Scalar fast lane保持到整个packet最慢lane可见，不能独立提前再用。

Exp callback执行原scalar_recipe的所有17个FP32节点（cutoff是1个）；每packet保守保留完整20spacing，cutoff也不会免费再用。counts分别记录full/cutoff lane数、compound请求及展开的FP32节点数。除法实际数值由原精确RNE oracle计算，时序仍是明确输入，不能把传入11当HardFloat实际延迟。

每次feed stall都断言callback计数不增加；每次held stall都断言实际word tuple和callback计数不变。输入转换只发生于accepted Matrix return；dot/score/output BF16转换仅作用于已退休的数值结果。max比较明确计数，仍未给比较/转换独立的物理时延。accepted callback失败后整份packet给零化error payload；ACK排空但不能publish。后到abort不改已有held words，通过sticky fault禁止publish。

这里的Python Q/K/V、scores/probabilities、4096cell以及held result全是host测试存储，尚未分配到原bank/register，feed_ready不证明有端口/带宽。没有输入DMA/输出DDR/Host完成ACK的实现；返回Result是测试返回值，不能称为Public completion。

## 原owner对照与整块账本

测试通过原 attention_matrix_batch 的AST抽取器执行原 OfficialAttentionOwner._attention、AttentionOwner._matrix_step和PrefixOwner._read/_write，保留原地址读写、softmax与BF16边界。独立Fraction FP32/RNE/FMA helpers来自现有原参考；candidate控制与原owner控制分开执行。同一测试同时检查每个score和所有1536/3072输出words。

首轮配置matrix=3/divider=11/feed=1/hold=2下，M1为98个Matrix step、3,072 selected FMA、214 Scalar packet；M2为198/9,216/436。ticks 1932/3964只是这份串行proposal输入参数下的模拟计数，绝非硬件测量、完整周期或利用率。

固定4096MAC资源和整块6,014,828,544 useful MAC分母保持原定义。M128 FFN另有71,680个SiLU向量、1,146,880次division；即使剔除division，SiLU服务下界也至少1,075,200，所有Exp全路径时2,293,760。此M1/M2 Attention测试不能消去这些成本，也未证明任何Dense重叠。完整账本见已发表attention_scalar_schedule.workload与attention_resource_audit；当前实际硬件周期未知，80/90%仍未接受。

## 复现

`python3 -S -B -m unittest candidates.qwen2_resident_matrix.attention_scheduled_numeric.test_ports candidates.qwen2_resident_matrix.attention_scheduled_numeric.test_controller -q`

`python3 -S -B -O -m unittest candidates.qwen2_resident_matrix.attention_scheduled_numeric.test_ports candidates.qwen2_resident_matrix.attention_scheduled_numeric.test_controller -q`

`python3 -S -B -m candidates.qwen2_resident_matrix.attention_scheduled_numeric.check_sources`

源门固定所有实际callback oracle源，包括此前补齐的PrefixOwner helper、前两份候选的模型/调度/测试，以及自身代码。只跑源门不执行数值。
