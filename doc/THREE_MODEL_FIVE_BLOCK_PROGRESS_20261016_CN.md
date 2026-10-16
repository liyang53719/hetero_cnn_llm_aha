# 三模型五类block：本轮计划与检查表

更新：2026-10-16。只新增状态快照，不覆盖冻结计划、源码或历史回执。
最终目标仍为同一固定配置/输入的完整实际RTL数值与状态PASS，以及
useful MAC / (4096 MAC每拍 × 完整block wall cycles) ≥90%；固定资源不能
按活跃lane缩小，DMA、stall、阶段间隙及最终写ACK均计入wall。
batch1/M128继续推进；1024/1224长序列待用户选择，不阻塞M128。

## 五类block状态

状态指完整业务接入/验收，历史组件或软件smoke不自动升级为当前完整block通过。

|目标|状态|当前真实边界与下一门|
|---|---|---|
|Qwen2-1.5B典型block，当前L0|ongoing|本轮推进Attention银行模型、packed原生微测及SFU候选；原业务M128仍待完成与postflight，实际RTL/90%未通过。|
|Qwen3.5-0.8B L0，GDN+dense|ongoing，本轮未变|历史真实payload与合成输入cold/carried/decode软件smoke保留；当前完整M128原业务/RTL资格不继承。|
|Qwen3.5-0.8B L3，Attention+dense|ongoing，本轮未变|历史真实payload、合成M128软件数值及组件工作保留；当前完整原业务/RTL资格不继承。|
|Qwen3.5-35B-A3B L0，GDN+MoE|to do，当前完整block|保留既有config/header/几何合同；真实payload、route/状态、完整数值与RTL/性能尚待闭合。|
|Qwen3.5-35B-A3B L3，Attention+MoE|to do，当前完整block|同上；必须使用真实路由与tile映射，不把Qwen2或0.8B结果迁移为PASS。|

五类均非done。范围来自[统一目标计划](three_model_typical_block_closure_20260917_zh.yaml)；
0.8B历史边界见[层0 GDN软件smoke](U00_2_GDN_PAYLOAD_NUMERICAL_20261006_CN.md)、
[层3软件smoke](U00_2_LAYER3_PAYLOAD_NUMERICAL_20261006_CN.md)。

## 已完成的小闭环与仍未完成的业务

- **done：synthetic bank-tiled M128数值模型。** `11257`主线基线已有
  [M128证据](../candidates/qwen2_resident_matrix/attention_bank_m128_evidence/README.md)：
  196,608个output word、99,072个score逐位匹配原owner Fraction参考；
  71,808 Matrix steps、7,168组/ACK。Q/K/V仍由host fixture提供，未证明物理供数；
  3,426,818 modeled ticks及Python耗时均不是硬件周期。不是完整block PASS。
- **done：panel M17/M32数值模型。** [独立证据](../candidates/qwen2_resident_matrix/attention_bank_panel_evidence/README.md)
  逐位匹配原参考。M32银行事务44,352→2,304，stage/舍入顺序保持。
  明确新增384 B，既有denseWeights物理复用未证明；panel M128、真实DDR/owner/RTL接入
  均未完成。测试使用的divider spacing=3是假设，不能带入性能结论。
- **done：packed profile2微型原生主机模型。** [原始证据](../candidates/qwen2_resident_matrix/attention_packed_native_evidence/README.md)
  为QK8/PV3全启用cell与Fraction比较、PV128边界及协议保持检查；默认profile0/1不变。
  不是完整Public数值PASS；`full_public_admission=false`、selected-fault发布时间尚未资格化。
  packed M128全启用FMA预期260,308,992，不能用selected-cell模型25,362,432替代。
- **done：SFU源审计及单上下文数值/边沿候选。** [审计](../candidates/qwen2_resident_matrix/sfu_microsequence_audit/README_CN.md)、
  [候选与资源账本](../candidates/qwen2_resident_matrix/sfu_silu_cycle_candidate/README_CN.md)：
  原16 divider/options0正常输入最少25拍；71,680个SiLU vector至少1,792,000拍。
  即使其余工作完美重叠，固定useful=6,014,828,544下上限81.9455%，故当前配置90%不可能。
  options16虽为14拍，但新增递推逻辑/时序成本，默认关闭；软件callback并非divider RTL等价。
- **ongoing：原始业务be00运行。** 来源为
  `be00eb8e4bc75e2e41f2a434d05d4c901ed3faa5`；本次更新最后已知进度为Attention PC12，
  结果及postflight待回收。使用[原launcher诊断](../candidates/qwen2_resident_matrix/raw_kv_public_recipe_run/numeric_progress.py)
  的进度口径；不能把阶段进入/返回、子模型PASS或后续主线CI绿色写成这次业务已通过。

## 下一步，保持默认关闭并逐项验收

1. **ongoing：收齐be00原业务结果。** 保存原数值比较、source身份、postflight与安全摘要；
   若失败，保留真实失败阶段。新候选不热替换正在运行的冻结源码，不据新切片推定旧运行PASS。
2. **ongoing：原owner可选packed接入。** 在原OfficialAttentionOwner及原Matrix服务上增加
   明确profile2路径，接真实DDR/共享银行与原输入，保留原算术、默认路径和完整golden；
   先补selected-fault最终发布围栏、返回/ACK/abort债务，再做有界全量比较。
3. **ongoing：A复用最小切片。** 按[源审计](../candidates/qwen2_resident_matrix/dense_a_reuse_audit/README_CN.md)
   保持同K的context-inner顺序；A gather从1,462,272降为298,496只是源级预期。
   首选Queue4→3加256 B hold，活跃payload 1280→1216 B；分别验credit、generation、
   stall/abort及原输出。cache不等于FFN重叠或新增SRAM端口。
4. **to do：W供数替代方案。** 先保留实际maxBeats16/1KiB配置，比较同K相邻context的
   row coalescing与另行冻结格式的tiled W；更大mailbox/多在途均须独立资源和协议账。
   原逐64B sole-active路径至少2,924,544服务边沿，A复用不会减少93,585,408 B的W。
   不将AXI内部在途数当owner并发，也不填理想DDR延迟冒充实测。
5. **to do：合并真实资源调度，再进入RTL。** panel384 B、A hold、SFU配置及三tile生命周期
   各自入账，明确bank读写冲突和返回保留。保持原数值门限，完成真实RTL全block数值后，
   再按固定wall起止测80%阶段指标与90%最终指标；任何孤立上界或软件加速均不能替代。

本文件仅整理已有回执/源码和当前运行状态，没有启动新的数值、native或RTL任务。
发布保留复现脚本、pins、hash与摘要，不附权重、输入/输出tensor或完整phase数组。
