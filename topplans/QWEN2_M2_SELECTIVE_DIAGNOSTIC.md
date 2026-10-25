# M2 selective 三臂诊断有限结果

父公开提交 bafb12b4cc0a14ad233602004e27adf65ad820cc。本片仅新增 candidates/qwen2_attention_selective_diagnostic 与本索引，既有 canonical 清单、源码、workflow 与历史失败不改动。实际运行与独审身份、计时边界及脱敏字段见该目录 README_ZH.md 和 evidence。

一组固定顺序 off/original/selective 的 owner-through-ACK-and-exit CPU 为 0.168004826 / 0.589193066 / 0.563943544 秒，不是稳定加速或采用证据。历史 synthetic fixture slowdown 继续保留；候选 default-off、不接完整 DUT。64 是逻辑测试身份，128 是两模式执行次数；没有打包重跑。

三臂 terminal、控制及组件 reference 的限定结果不替代完整 M128。两 observer 的 frequency 相等；reference normalizer 重复 8/16 次、DUT 每值一次，值及 presence 一致，不声称 reference frequency 相等。原 full M128 CPU 超限 FAIL、r1 BLOCKED、无原生最终 seal 的限制全部保留。没有长跑重启、预算增加、RTL、硬件周期、80%/90% 或有效 MAC 验收。
