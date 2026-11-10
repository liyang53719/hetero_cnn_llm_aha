# 原Conv真实生产者贯通：精确范围PASS

- done：原Conv owner真实写回→RawPrep16heads→selected head0两chunk phase1–17→state export，M128；78,183,169周期，774,339读、104,320次64字节写逐beat比对；exit0，stage1638.15s。
- done：首跑cycle2是driver先观察旧response.valid导致组合unknown暂态，证据保留fail_first。修复先驱动再观察；前后SV同hash，原DUT/Legacy fatal0不改。
- PASS仅合成Dense QKV/AB和合成Conv权重边界的该连接子链。实际由Chisel发射SV再Verilator执行，非纯解释模型。
- todo：接训练权重真实Dense前缀和后半完整block；其他heads需重测，不能迁移旧原全16 underflow FAIL。
- 五块128完整回归0/5。未证明同4096物理资源/最终共享RTL完整数值/80%或90%有效MAC利用率。
- 无生成数据上传；临时数据保留。
