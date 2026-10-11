# 同形状 QK 与 BF16 舍入差异

`ATTRIBUTION.json` 原样保留，SHA256 `2e5991c9efb31e980c8ef9199717b6c7a0e4d58b91f3bcfd5faa4086d2c3519a`。
它只包含固定版本、运行身份、形状/stride、哈希、选定标量及统计；没有原始张量、模型权重或编码数据。

原 JSON 顶层 scope 写的是 selected cells only。后续附录 `full_shape_single_operator_replay` 实际还执行了一次完整形状的孤立 QK matmul 加 scale；该附录重现 393216 个保存分数的全部字节。这里明确更正范围，不修改原记录/hash。没有重跑完整 block。

原 forward 没有直接保存 stride 或内部 FP32 accumulator。重放的 stride 从冻结源码推导；完整输出一致是重放证据，不是内部归约树观测，也不区分形状和布局各自的影响。所列小形状结果仅作反例，不替换完整形状 oracle。

数值候选仍为 `DIAGNOSTIC_NOT_ACCEPTED`。原 v0 合约、逐节点/末输出门及旧 FAIL 保持。参见 [中文决策材料](../../../doc/QWEN2_BF16_NUMERICAL_DECISION_20261011_CN.md)。
