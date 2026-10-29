# 2026-10-29：固定源码清单纠错与性能静态上界（INCOMPLETE）

## 必须纠正的清单身份
7a22ccc14d6d269262ecf5756488c81e8e4ccfc4 发布的 `candidates/attention_policy_count_fix_20261029T0054/SOURCE_OVERLAY.json` 中，DiagnoseOriginalHostMoePhaseV5.scala 错配为旧 192MiB artifact-cap 源码 SHA2380c88d…；实际编译/原始high发射使用的是已发布 384MiB helper SHA8807829a…。

该错误来自沿用旧来源清单，不能再把旧 SOURCE_OVERLAY 称为实际155源编译闭包的精确身份。旧文件作为历史证据保留、不静默覆盖；**以本目录新 FIXED_SOURCE_OVERLAY_R2.json 和其验证器替代用于后续恢复**。旧清单所声称的精确来源对应关系撤回，而不将已生成结果重新命名或伪称重跑。

## done：独立核验的精确范围
- 新旧 helper 源码逐字节仅 `bytes.length<=192L*1024*1024` → `<=384L*1024*1024` 一行变化，是已序列化单产物大小上限，不是硬件结构或数值算法。
- 对实际预算helper编译产物的三个 SourceFile=DiagnoseOriginalHostMoePhaseV5.scala 类逐一查 JVM 元数据和 SHA，与 fixed_production_classes 及固定编译类 receipt 完全一致。只记录哈希，不提交class。
- 155项清单仅修正该 helper 的repo路径/blob/SHA，其余154项不变，包括 attention 进位修复源8cea…；新清单仍对应同一固定4096 MAC硬件，未按模型重elaboration。
- 已生成 fixed high/SV 的实际产物hash不因清单纠错变化；不将静态清单测试当重新发射或数值回归。完整 Chisel block M128 和最终冻结 RTL 数值仍 **0/5**；独立官方 Python 参考 **5/5** 仍仅参考层。

## 新增性能审计：静态条件上界，不是RTL实测
`../full_block_source_utilization_bounds_20261029/` 保存完整block Matrix MAC数量、GDN各阶段读写/vector事务计数、条件上界脚本和关键复核。固定分母为4096×完整block周期；不把Vector/Scalar工作计入Matrix有效分子。

- M128原始GDN路径是两个64-token chunk，由前块 next_state/ACK依赖衔接，不是循环M1冒chunk。
- 当前issue与wait状态互斥，无同拍retire旁路，事务至少2周期的静态下界适用于当前映射；不是最终测得周期。
- MoE226/218 active experts来自本次原始Torch参考，对应该输入的条件几何上界；不能推广为未来统一架构极限，也不构成同分small-ID契约同意。
- Attention矩形/因果有效MAC分别列示，shared gate逻辑N1与物理N32分开，padding不得充当有效MAC。静态界已显示当前路径不足以宣称80%/90%达标。
- 100GB/s等供数情景仅假设敏感性边界，不是目标内存或LPDDR实测；没有完整RTL周期、性能或数值PASS。

## ongoing / todo
1. 继续真实固定4096数值backend编译与五块完整128回归，复用组件必须核实际源码/产物/tool/flags/hash；旧16lane PASS不迁移。
2. V3最终状态driver未native编译、未执行DUT；参考与硬件严格分层，不用软件算术替硬件。
3. 根据静态瓶颈继续评估共享32-lane每周期发射与64-lane两周期发射、tag/credit/outstanding、精确Div/sqrt、跨tile驻留与就地BF16，不擅改精度/归约。
4. 五块模型数值全部通过后才冻结，再同一份最终RTL同刺激回放。MoE同分参考契约和第二档1024/1224仍待明确，不阻塞128其余工程。

本次仅新增源码/pin/hash/摘要，不提交IR/SV/classes/权重/NPZ/探针数据；不覆盖旧证据、不清理、不改历史、不重复CI/EDA。
