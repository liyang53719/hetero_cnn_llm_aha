# M2 identity-lookup 有限实际诊断

父公开提交 2a898bb742d0b71beeae9115933054e27952a5ef。本片只新增 candidates/qwen2_attention_identity_diagnostic 与索引，不改 canonical 状态、生产路径或 workflow。

唯一固定顺序 off/original/selective_identity_r1 的 owner interval CPU 为 0.147838387 / 0.647338533 / 0.471684661 秒。original→identity 同次差异包含 selective-LINE 与 identity cache，不能当 cache-only 因果贡献；R4 不在同次三臂内，跨运行计时不能用作受控分母。无稳定加速、采用或稳定性研究结果。

22314 项实际独审、115-artifact 外置 ledger 只覆盖既定 M2 组件证据。reference normalizer 8/16 次与 DUT 每值一次的频率区别保留；完整 M128 CPU FAIL、fixture slowdown、r1 BLOCKED、无原生最终 seal 仍不变。源码可由 7 个新原字节文件与 13 个已有公开引用精确组装，20 个 packaging-only 测试不是目标验收。无 RTL、硬件周期、有效 MAC 或 80%/90% 结论。
