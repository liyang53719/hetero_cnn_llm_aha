# 原始完整 Public M128 packed 程序接入（进行中）

以已通过完整M16业务程序的精确HostControl PrefixJob修复为起点，应用已通过M17/M32实际Public transport数值验证的16-key分块schedule。继续使用同一父owner、Banks、全enabled-cell native Matrix和原始Scalar算术。

已完成：独立M128参考资产复用准入与十字段观察器的冷检查、345项完整源码闭包、原始执行/比较代码的精确选择替换。5项 normal/-O 冷测试通过（33.169/33.246秒），包含实际HostControl M128请求、真实入口/official/fullgraph/admission/contract五条源码映射相等、源文件漂移与跨M16 profile拒绝。进行中：完整entry独立复审与真实Git上下文的准入预检。拟议预算为内部2400秒、外部2430秒，必须单独批准后执行。当前没有完整M128程序结果；既有M16及M17/M32结果不被继承成M128验收。

不引入A-hold或改变算术/参考阈值。完整21事件、27项assigned/28项observed门限保留；full29与RTL验收仍分别报告。

## 已有实际证据与本次边界

已完成：修复精确HostControl PrefixJob准入后的完整M16程序，21次完成、17个owner job、27项assigned official门限和28项observed阶段通过。该次实际外层591.280秒，完整terminal569.198秒；不是M128结果。

已完成：新tiled schedule的M17/M32真实Public transport，全部score/output与原始Fraction参考逐位相同。M17含两个key16故障drain，M32执行21,037,056个enabled-cell FMA；七边停顿期间真实raw response和PV context保持。独立证据另存attention_packed_tiled_evidence。

成本审查：Dense的固定N/K仍发1,462,272个物理packet，即5,989,466,112个native FMA；M16的padding也实际计算。M128增加A ingress、输出、SiLU和Attention工作，不能按总时间简单乘8。新Attention预计71,808步、260,308,992个物理FMA；2400秒只是拟议上限，不保证完成。没有新增A-hold、并行免费算术或利用率结论。
