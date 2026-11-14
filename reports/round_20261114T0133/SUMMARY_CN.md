# 2026-11-14 01:33 hetero：INCOMPLETE

固定4096 Matrix MAC、同一候选硬件定义未改变。五块M128完整原Chisel数值仍0/5；完整RTL及完整block有效MAC利用率未测。Python参考、候选编译IR及RTL层级不混同。

## 实际新增工作
- L0：真实候选Conv输出后，完整M128×16×128 Q/K归一化独立Fraction参考完成。实际16-head路径从源码确认选择ascending/gate0，Q scale为0x3db504f3。Q/K SHA分别788717208626c43bc7c697bac3aab055c7727efc61db06d9f80fd4f3475161a4、0e05d86628973c5feda0ad5b4d8879247337baa0436ab841663ec62ac99fa9cd。该子阶段仅0/NX；未执行gate/Softplus/A_log/beta，不能称完整RawPrep或历史head4重现。原strict FAIL不变。
- 另一个源码归约序仅对照，未运行Torch；Q/K分别137157/150326 FP32字不同，没有切换冻结参考。
- 35B：新增离线契约检查代码，4测试通过，包括真实profile3/4 metadata、12坏descriptor/arena变异、640个M1..128×5 MoE Dense几何检查。6MiB phase DDR不与输入重叠，八权重及padded gate布局合法；固定768KiB Dense SRAM可驻80行，M128为2行批次，无新增Matrix。不是DUT执行或周期利用率。
- 安装门不能仅放宽：现有MoE硬件路径存在，但router源码明确P7 exp和stable-ID tie未证明原Torch等价，后者仍待用户明确。当前未写开门候选、未切OfficialBF16或盲开Qwen2 resident/transposed。最小后续是独立拓扑能力判据、构造交叉约束、保留真实phase/lease/ACK/fault，并先补数值资格。
- Qwen2 20份及L3 56份已有完整独立分阶段参考重新hash一致；没有重算或作为硬件PASS。现有checkpoint schema 2项/4故障负例重跑通过。

## 任务和证据边界
旧29364终态未知，未重启。新当前候选独立有界任务52143 exit0：从cycle439无reset/relaunch续至9266首真实B-ACK64B，保存完整20块含非空scratch；fresh-process续120周期至9386，ACK共320B（80个FP32字）与独立参考0 mismatch，连续/恢复轨迹和最终20块hash相同。首RMS尚未完成，不是完整M128长跑。35B真实权重仍缺，未重试受限网络。

## 远端与清理
基线main f9375f0e067829e60d424b9ab328f48dccbe94d4，CI43535778709 success，仅payload守卫。工作树clean；临时清单已核，清理0，保留原日志/源码/数据/运行文件。本轮远端仅允许摘要与计划，不上传候选源码、权重、NPZ、生成数据或原日志。
