# 官方 fresh M128 paired reference：源码 / mock 阶段

状态：r2 source/mock审查通过，尚未实际构造或运行M128官方层。无M128数值参考、无DUT PASS、无执行GO。

当前包：[独立M128源码与说明](../candidates/qwen2_official_m128_reference_pair/README_ZH.md)。它不改变已发布M16包或旧pins，不继承M16 PASS或一次执行许可。

1. 原官方完整layer，原config32768/rope1e6，原embedding rows[0,128)，一个真实chunk128。
2. 同一layer/inputs baseline→observed两forward；实际y/prob逐字及三边界状态比较；observed全29，非all29 baseline无干扰证明。
3. r1终态预算漏检已由r2修复：父receipt/seal精确字节投影、写后核验、最后seal发布；失败保留证据且无成功seal。
4. 公开18项轻mock通过普通/-O，仅10项保留终态mock+8项新source/逻辑检查，不声称复现私有原92或独立9。
5. 本次冻结公开后像仍保留60CPU秒/90wall秒等r2候选。资源选择与后续finalprofile单独推进，需新exact review和一次root GO；此source publication不批准执行。

下一阶段：冻结独立final运行profile与完整闭包配置，复审后再申请一次受控官方M128 pair。超限留FAIL且不自动重试。原始阈值不变。
