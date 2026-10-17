# M128 run 准入实际探针回执

已完成：真实 Git/原始资产条件下，修复后的实际 entry.run 经过真实 verify_snapshot，第二次 runtime 调用前由专用哨兵停止。第一次 runtime 已正常返回；没有创建数值输出目录、载入 DUT ELF、提交数值任务或执行 RTL。

实际探针24.208482秒，350个源身份，13个负例全部按预期原因拒绝。负例包括行数、canonical模式、跨profile、缺失真实M16前提、缺失origin、独立参考digest、主参考identity以及源漂移。两个reference负例在第一次runtime之后按相应身份检查拒绝，避免把缺少frozen_sources误当成正确拒绝。

EVIDENCE.json只保留hash、计数、固定原因和范围；不含绝对路径、张量或权重。原失败346源回执仍独立保留，本回执不会把那次失败改写为成功。该探针证明准入路径，不是完整Public数值成功。

复核命令：设置 PACKED_M128_ADMISSION_PROBE 指向原PROBE.json，然后运行 python -m unittest candidates.qwen2_resident_matrix.attention_packed_m128_admission_evidence.test_evidence；再以python -O运行。同源原回执外部比对已完成，独立评审与原回执2+2冷测已完成。
