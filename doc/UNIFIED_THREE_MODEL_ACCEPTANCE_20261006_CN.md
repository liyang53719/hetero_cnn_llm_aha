# 当前统一验收目标（2026-10-06）

本报告落实用户对两个项目的一致目标；此仓库独立保存和验收自己的证据。
目标为 Qwen2-1.5B、Qwen3.5-0.8B、Qwen3.5-35B-A3B 的典型完整 block。
每个必需 block/workload 必须同时满足实际生成 RTL 全量数值/状态通过，以及整 block 有效 MAC 利用率至少 90%。
源码、HLS、E0 模型、组件 canary、旧合成回执均不能代替这一最终结果。物理时序/功耗仍单独报告。

## 当前来源与支持边界

- Qwen2-1.5B：既有精确身份为 Qwen/Qwen2-1.5B-Instruct，保留 Instruct/Base 区分。固定 revision/config/framework 哈希记录在 `config/qwen2_1p5b_target_shape.json`。沿用 B2_DENSE 的完整 Attention/SwiGLU、Norm、bias、residual 与 KV 提交边界；现有合成几何通过不代表当前官方 checkpoint 或 90% 通过。
- Qwen3.5-35B-A3B：已有 `config/model_profiles/qwen3_5_35b_a3b.json` 与 `reports/execution/QWEN35_REFERENCE_LOCK.json`。后者仅 metadata，明确没有权重和数值 RTL 通过。需要 B35_ATTN_MOE 与 B35_GDN_MOE，包含 routed/shared experts、route 与必要状态。固定原字节和当前权重来源仍需复核。
- Qwen3.5-0.8B：当前仓库没有该型号的 pinned profile、固定 revision/hash 或已接入 runner。本次不填猜测的 shape。官方可变 main 配置可作为 U00 的读取线索：https://huggingface.co/Qwen/Qwen3.5-0.8B/raw/main/config.json 。只有冻结官方配置/forward/层索引后，才能正式选择 Attention+dense-FFN、GDN+dense-FFN 等该型号真实存在的 block，不能从型号名或35B配置推断。
- Qwen3.8：保留历史研发任务、六类 inventory 和原证据，已从当前必需三模型及派工队列排除。它不能替代 0.8B；旧 R00、整网/视觉/MTP 发布不代表当前 U01 通过。

## 利用率及同源门禁

当前可复用的主计数口径来自 `src/heteronpu/block_performance.py`：

`Matrix useful MAC / (该次生成RTL固定配置的Matrix MAC每拍 × 整block wall周期)`。

- 固定资源数来自本次实际 DUT manifest，不能换成活跃 lane 数，不能混用 4096-MAC、512-MAC 或其他项目的配置。
- 从 block launch 握手接受起，到最终输出和必要状态写 ACK 全部完成止。descriptor、DMA、内部 stall、阶段间隙、padding 与 drain 都必须在分母里；不得只截 Matrix 发射窗口。
- 原计数器包含额外启动空拍的历史记录保持原值。新增回执要保存实际起止事件，不能从旧数据中无依据扣掉周期。
- executed MAC 利用率、useful/executed 和 active-window 可旁报，不能替代主门禁；padding 不能算 useful MAC。
- Matrix 与 Vector 单列。Vector 需冻结实际单元数、MAC/非MAC操作单位和计数来源，同用完整 block wall 范围。现有 SiLU `usefulMacs=0` 不能证明 Vector 利用率，非MAC操作不能折算进 Matrix 分子。
- 数值与性能必须绑定同一 model revision、官方 config/forward、layer/block、batch/query/KV、dtype/精度策略、权重/输入/初始状态、cache/内存条件、生成 RTL、source/tool 哈希和资源配置。
- 必需性能 workload 集合在执行前冻结；0.8B合同、token集合、路由/初始状态或Vector计数未确定的地方标明 BLOCKED/未测，不能事后只挑最好长度或用其他模型代替。

## 不能被旧结果掩盖的差距

现有 Q2 冷 N16 两层归档为 1,498,202,112 useful MAC / (4096 × 16,639,515 cycles)，约 2.198%。
98.30% 是 useful/executed，绝不是整 block 利用率。不改变流量及该通道假设时，理想上界约 11.824%，也低于 90%。
来源为 `reports/execution/BLOCK_CHECKLIST_ADVANCE_20260917/P00_1_counter_audit.json`。不改旧记录、不降低新门限；需要实际数据面/复用/映射改善后重验。

MoE 必须增加真实路由 histogram 与实际 tile 映射可达性检查。以假设均匀路由为例，M128、Top8、256 experts 仅平均4行/expert；若另假设64行tile，行占用仅6.25%。
这是条件算例，既不是实际路由，也不是 hetero tile 配置。它说明仅重排调度未必足够，需实测小M映射/packing与固定资源下的 useful MAC；不得把padding计入有效工作。

## 计划与清单落点

- `doc/three_model_typical_block_closure_20260917_zh.yaml` 的“当前统一验收目标”优先于历史六类发布范围，修正 G8/性能目标旧表述。
- 新增 U00“冻结当前三模型合同与回放工作量”、U01“三模型典型block数值及90%联合验收”，均为 to do，未执行模型实现。
- `doc/block_checklist.yaml` 更新计划 SHA，保留所有已完成子项及原证据；当前队列排除历史 Q38/R00/F00/F01。
- 计划校验器检查三模型、90%、实际RTL、固定资源/完整周期、Matrix/Vector分报、必需来源字段，以及U01不依赖历史Q38闭包。校验 PASS 仅代表文档合同一致，绝不代表硬件 PASS。
- C03.3 仍仅为 synthetic E0 shape/layout 与宽地址向量完成。C03.2、官方模型真实接入、三模型数值与90%尚未关闭；Chisel CI另跟踪实际运行结果。
