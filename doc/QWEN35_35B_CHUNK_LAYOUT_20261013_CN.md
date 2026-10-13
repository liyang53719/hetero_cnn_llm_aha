# 35B 32头 Chunk 布局与事务增量（2026-10-13）

## 本批只关闭布局接入的小门

ChunkJob、ChunkOwner、TypedChunkDriver显式绑定immutable PrepLayout；0.8B默认保持。
35B输入真实地址使用51200B/token、Q/K/V各4096个FP32元素、gate起点12288。
Prep已将Q/K重复到32个value head，Chunk读取head本身，不能再次head//2。
32头layout要求全部32head；用于快速事务测试的dk16/dv32显式标为synthetic reduced dimensions。
完整35B dk/dv仍128，不能把小维度测试当完整模型数值验证。

## 真实执行及容量边界

本批实际执行一个M2合成输入，32头、dk16/dv32，每头真正完成一个带62个padding行的chunk64。
两token各有唯一head/value哨兵；所有320个真实source读beat地址精确核对跨token和head15/16、31边界。
输出BF16和完整65536B合成state与独立二步解析公式逐字节相同；scratch每beat真实写入并ACK。
这是地址/事务/状态分区小测，不是M128 prefill通过，也不是官方checkpoint或RTL验收。

实际M2小维度结果：source读20480B，scratch读70303744B，总读70324224B，写5312512B；
2363649 software transport ticks，32个chunk完成。state/output/scratch均保持未published staging。
Vector16固定一份、Scalar沿caller复用，Matrix不调用。1KB转置tile仅指tile payload。

完整35B容量检查（未执行完整维度的数值计算）：

|规模|input|state每副本|BF16 output|scratch DDR|
|---|---:|---:|---:|---:|
|M16|819200|2097152|131072|27918336|
|M128|6553600|2097152|1048576|53739520|

这些DDR容量随heads增加，不能说总体存储不增加。cold逻辑state_in仍检查互斥span但不读取。
32头state每副本2MiB，M128 scratch为51.25MiB，不是新增片上SRAM或已证明的硬件缓存容量。
当前generator还有至少九个跨yield FP32 list和adapter缓冲，物理寄存器/live-list总上界未证明。
这项是“硬件对应模型”的证据缺口，不能仅凭Vector16固定就宣布全模型固定硬件资源闭合。

## 故障与生命周期

layout错配/运行中替换拒绝；reset保留选定layout。实际source读错误释放同Scalar/Vector，
不发布输出或state。另有明确transport-only脚本：在完整dk128/dv128容量的最后scratch beat和
最后state beat实际发写，尾state ACK错误后drain且不计成功ACK，任何span不发布。
该脚本不执行算术、不覆盖完整state，不能与M2数值例合并宣称全维数值通过。
首轮脚本误用无send的tuple iterator失败，改成真实generator后重测，不继承失败PASS。
原所有状态仍由最终完整block joint fence负责，局部Chunk成功只返回staging receipt。

## 数值与后继接线依赖

官方35B与0.8B的torch_chunk_gated_delta_rule完整函数AST相同，但仍需要35B source/config/runtime身份。
本批没有改变旧exp_negative（绝对值≥80归零）或逐项FP32 cumsum。真实35B已有g≤−80，
不能因Prep双exp改善便认定chunk自动用新exp，也不能把同函数AST当数值通过。
官方固定CPU的FP32 cumsum实际用FP64 running，每项输出转FP32后下一项继续用未回写的running。
它与Q/K sum的FP32 8lane归约是两种不同策略。

已有完整链门必须逐项保留：BF16物化节点和最终输出原门、FP32 state原公式不得放宽；
Prep和same-input standalone chunk尚无独立已批准官方门，只诊断。完整35B MoE的routing/selected
experts/shared expert和离散语义验收清单仍需建立，不能借0.8B Dense清单代替。

后继真实接线必须在同一次生产者调用尾部继续原memory/Scalar/Vector与已ACK Prep Region；
不能导入saved raw并伪造生产者。现前缀通用run要求output已publish，Chunk刻意只返回staging，
需要staging-aware交接，不能为迁就helper提前发布state/history或增加generation。

## 运算计数与硬件证据层级

合成小例Vector issue：Mul944128、Add1000448；有效lane操作Mul15106048、Add14947328。
主机批处理mul_add调用914432次，每次16lane，等于14630912个分别舍入的Mul→Add对；不是FMA。
额外逐元素缩放与门运算不混算到这组paired MAC。Matrix有效/执行MAC均0。
尚未为该合成缩维/填充算法分配semantic有效Vector MAC合同，因此不伪报有效利用率。
software ticks未包含真实算术流水/存储延迟，硬件完整周期、占空比、80%/90%利用率均未知。

原门精确数值与出处：spec/numerical_contract.md、full_compare.py291–365：
- 已分配BF16节点：max_abs≤0.03125、mean_abs≤0.005，NaN/Inf拒绝。
- same-input Conv/SiLU：≤1 BF16数值ULP，signed zero位差另列。
- 完整链FP32 state：每元素abs(a-r)≤1e-4+1e-4*abs(r)，不是bitexact门。
- 最终完整block BF16：max_abs≤0.05、mean_abs≤0.01，不能绕过已分配中间节点门。
这些原公式可保持用于新35B原shape/纯官方端到端参考的兼容检查；本批没有执行该检查。
Prep及same-input standalone chunk仍UNASSIGNED，不能挪用上述其它边界的门。

## 回归证据

最终冷门实际538项、50套、151源码，零skip且源码前后不变；指定计划清单91项通过。
机器摘要的M2执行记录绑定最终冷门四项grouped测试日志；含reset身份和尾ACK错误测试。
冷门仅合成软件范围，不把上述计数扩大为checkpoint或RTL验收。
