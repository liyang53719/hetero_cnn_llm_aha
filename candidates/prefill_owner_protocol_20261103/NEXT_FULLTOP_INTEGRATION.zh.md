# 下一完整 prefill 链集成门（未准入、不是本次 owner 协议结果）

本次发布保持所有既有共享生产入口与旧证明域不变。独立六源候选、selected159和owner协议测试不会自动获得新完整block构建/数值资格。保留本地完整integration.patch作为后续专门集成输入，不用它覆盖已经包含finite-long修改的main。

1. **真实共享选择/生产链。** 在最新main三方合并 `candidates/model_candidate_build_20261101/{candidate_generation_gate.py,bootstrap_model_candidate.py,prepare_model_build.py,materialize_model_binding.py,restore_model_inputs.py,pack_model_candidate.py}`。对原legacy/address、原readonly/finite-long组合做保留回归；restore固定gate SHA必须对应合并后真实字节，不复制旧pin。
2. **精确新producer身份。** `candidate_dependency_proof.py` 的selector/finite/readonly实现map、`LOCAL_PACK_READER_SHA`及compilation_policy keyset必须为新实现建立独立版本，保留所有旧map和旧artifact读取域，拒绝未知/交叉配对。先证明旧generation在新helper下不回归，再引入新supply域，不泛化hash门。
3. **新硬件source-observation合同。** `model_source_evidence.py` 的SCALA角色以及对应P0 source contract/GENERATION_CONTRACT/consumer binding必须明确新的HostBlockTopV4、QwenOwnerProtocol等源身份。仅更新source catalog不够；旧合同正确拒绝新源，不能跳过。所有新manifest仍保持numeric_execution_authorized/final_rtl_accepted为false，直至各自实证门完成。
4. **同硬件一次全Top结构构建。** 以同159 source、正确tile地址、原4096MAC/Vector32/A16×1376×256/B16×160×256/122外部ports发射一个统一Top，五profile共用SV，不为模型单独elaboration。将新增1KiB W queue与metadata实际计入资源，实际检查所有owner/DMA/top新snoop和读债连线。只能独立云端有界阶段或原FULL结束后准入，不挤原FULL资源。
5. **真实DMA和tile路径协议回归。** 当前8case未包含iDMA/TileSumBridge。后续必须覆盖实际单descriptor adapter的posted W收取/外部串行服务、ordinary/stream同时offer、读错tag/LAST/backpressure、prefetch在旧writeACK前且新group仍等完整fence、A snapshot同cycle失效/FP32外存单位、QKV窗口snapshot接续、K1536边界和slot2 partial/add/drain次序。不可用owner mock memory的并行服务冒目标内存带宽。
6. **五块同刺激数值和周期。** 在用户已批准原始reference/路由/FP32-BF16精确算术次序下，对Qwen2-1.5B、Qwen3.5-0.8B L0/L3、Qwen3.5-35B-A3B L0/L3的M128完整block逐级验收，复用一个统一SV和真实刺激；原FULL的旧源结果不可转移给新硬件。计数须以固定4096和完整block周期分母区分理想供数、压力bench、目标内存、预测与RTL实测。

仍需架构工作而非资格扩展：当前burst布局的P0 Q乐观界约61.6579%，不能承诺80/90%；小m routed MoE的M128几何浪费与唯一权重带宽、窄N的反馈延迟都未被本次owner8case解决。后续需要真实可配置packing/驻留/供数改进并保持路由/tie/算术顺序，不能把资格PASS当五块有效MAC目标达成。1024/1224长token另列，不能阻止先完成M128，也不能假称已解。
