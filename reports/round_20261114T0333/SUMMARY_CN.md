# 2026-11-14 03:33 hetero：INCOMPLETE

固定统一4096 Matrix MAC；五块M128完整原Chisel数值仍0/5，完整RTL及完整block有效MAC利用率未测。当前候选不能迁移历史strict通过。

## 真实Host数值进展
当前候选从实际保存cycle10266完整包恢复，无reset/relaunch、不重算前缀。session57210 exit0，新增1565周期/13.018秒至11831：首RMS第1/128行完整1536 FP32、6144个真实B-ACK字节与独立参考完全一致。完整20块checkpoint已保存，SHA08e35d53b2253e73048c72dd9793b98f73e0b3851b41a857424dc5bd0353356d。
新进程恢复后续120周期至11951，继续轨迹及20块序列化终态hash一致，既有ACK保留；没有完整首RMS或block通过。参考只核实际写回，未供DUT中间值。

## 独立主线
L0实际16-head绑定Chunk strict vectorPolicy0、cumsum0、decay0，不把RawPrep MulIeeeRne候选UF政策延伸至Chunk。真实prepared输入的head0/chunk0（64行）phase1/2独立参考已完成，仅0/NX，随后按原调度phase5完成，phase6 row52/colBeat1/lane12最终pair-factor Mul出现首个UF|NX：0xb90b2091×0x05d1243c→0x801c6a52 flags3，独立精确见证已复核。strict vector0应拒绝，未继续phase7/head4；这是当前候选输入链独立参考的新FAIL，不是历史同刺激故障重现。没有放宽策略，不以两段单token冒chunk。历史strict head4 FAIL保留。

MoE新增Fraction逐步FP32 P7源码配方重放2150个输入，与已有NumPy P7候选字相等；相对高精度理想exp诊断20个字不同，样本最大1 ULP，不是全域界限，更不是原Torch结果。5个256-logit边界概率行中1例有1个概率字不同，cutoff集保持但同分未获授权，不改变ID基线。902个内部UF仅独立节点诊断；compound exp的primitiveFlagsValid=false，不能称硬件fatal。冻结Torch库缺失，未复验原kernel、未开准入门。

## 阻塞及维护
旧29364原身份仍Unknown未重启；35B真实权重缺失，MoE数值/tie资格仍阻塞。Qwen2/L3既有完整独立参考复用。
基线main7ab8eebfc24e1a2e6b9732cc1cfd4a96ef02800b，CI43546909350 success仅payload守卫。工作树clean，临时清单已核，清理0，保留唯一证据/源码/运行文件；远端仅允许摘要及中文计划。
