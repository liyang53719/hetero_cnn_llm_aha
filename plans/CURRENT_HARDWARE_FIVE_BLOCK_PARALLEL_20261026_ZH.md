# 五类 block：原始 Chisel 完整 M128 数值后再 RTL 回放（2026-10-26）

## 当前执行顺序：先原始 Chisel 数值，再 RTL 回放

按 2026-10-26 15:56:30 / 15:57:17 UTC 的最新用户要求，**五个 block 可以并行；验收顺序是原始 Chisel 完整 128-token prefill 数值回归 → 冻结同源、输入和参考 → 生成 RTL 并回放五块数值回归。** 五个 profile 为 Qwen2 L0、Qwen3.5-0.8B L0/L3、Qwen3.5-35B-A3B L0/L3；不能把单个 leaf、mock 控制测试或独立 Python/C++ 软件模型结果当作原始 Chisel 整块通过。

1. 保留并复用 Qwen2 已修 92 源的既有 prefill 能力：`HostBlockCommands` 的 public21 入口允许 M16/M128，`Qwen2Block` 已有跨 token 的 Norm/RoPE/Attention/SiLU FSM；它并非只有 M1。该代码仍受固定 Qwen2 shape 与内部算术约束，须接入五 profile 统一 runtime / 共享 4096 资源，并保留原 QKV 分段归约语义，不能以普通 dense 求和冒称等价。Qwen3.5 原始 block 适配入口的 M1 限制单独处理。当前补齐原始 `HostBlockTop` / `HostBlockCommands` / `QwenOwnerKernel` 到共享真实数据 owner / Matrix 与公共 runner 的统一接线、完整数值闭环；五 profile 并行且不互借 PASS。
2. 五块原始 Chisel 数值门通过后，固定同一份源码身份，并冻结各 profile 的输入、权重、官方参考及批准比较合同；不把用户指令或待执行配置记为已完成。
3. 再生成并固定**同一完整 4096-MAC 硬件、同接口、同 RTL hash**，只切换 runtime 配置与权重，回放同一批五块输入/参考。仍需独立 RTL 数值证据；Chisel PASS 不自动继承为 RTL PASS。

当前公开主线基线为 `56f4e11ed805f96dc2f1e50384cc7f832012bfca`。根 `chisel/continuous_prefill/` 的 455 个文件相对 `c590179c4c3424ded9997ba8f15f27821df304c9` 均为相同 Git blob/mode；这项裸根目录身份事实不等于上述已修 92 源 overlay 已被直接安装到根目录；后者按 [公开来源重组流程](../candidates/qwen2_ordered_vector_compile_evidence/README_CN.md) 复现，72 个公开 recipe 源加 20 个原 pin 的外部 HardFloat 源单独绑定。后来发布的 admission、state、GDN、MoE、共享 fabric/controller 候选也不能冒称已经接回原始完整 block 入口。本段确认既有源码能力，不新增任何 Chisel 数值 PASS。最新结构/ABI/Yosys前端结果只按各自范围收尾归档，不升级完整 block 数值，也不另开 EDA 主线绕过上述顺序。

此处只纠正执行顺序与导航，`doc/block_checklist.yaml` 的 74 条任务及全部 `to do/ongoing/done`、旧 FAIL/TEMP、固定 4096 有效 MAC ≥90% 目标保持不变。五块原始 Chisel/RTL 联合完整数值验收尚未建立；既有软件观测域或有限 leaf PASS 不回填该缺口。

## 历史 06:04 / 06:36 执行导航（顺序已由上节覆盖）

按 2026-10-26 06:04 UTC 的用户新要求：**继续核验当前真实硬件结构能否生成 RTL，同时并行推进其余四类 block；不再让它们等待 Qwen2 主线完成。** 旧文档中的“先 Qwen2、再其余模型”保留为历史时点说明，不再作为当前派工依赖。

**最新硬约束：直接验证完整 4096-MAC 配置。五个 profile（Qwen2 L0、0.8B L0/L3、35B L0/L3）必须使用同一份硬件、同一个接口和同一个 RTL hash，仅 runtime 配置及权重不同。** 不允许分别以 16/32 head 的 elaboration 生成两套电路再声称满足“通用硬件”。固定最大 32-head 容量、5-bit 索引与 runtime heads 的共享 state 控制叶已独审并发布（7bf6fc287ba9e7b5f696c44a691f432a3e3958c4）；仅同一叶实例 runtime16/32 控制范围 PASS，不代表完整 4096-MAC 五 profile 通用 top 已接入或数值验收通过。

此前单 512 endpoint 的 lint 候选已撤销且未运行，不能继续作为当前执行计划。旧按 16/32 分别 elaboration 的 state32 九文件方案已暂停，不随本批发布为解决方案；toy/DPI 冻包继续保持未发布。

| 分支 | 当前安排 | 本片授予的实际资格 |
|---|---|---|
| Qwen2-1.5B 典型 block | 真实 Matrix 硬件生成、provider 结构与资源风险继续收口 | 下述限定的重发射与源码重组；不是完整 block RTL 数值 PASS |
| Qwen3.5-0.8B L0 | 与主线并行核查源码、合同、测试及当前阻断 | 本片不纳入新的模型实际验收结论 |
| Qwen3.5-0.8B L3 | 与主线并行，单独保留证据和失败 | 同上，不借用 L0 或 Qwen2 结果 |
| Qwen3.5-35B-A3B L0 | 与主线并行，区分共享部件与完整 MoE | 同上，router 冷门通过不等于 MoE 实际通过 |
| Qwen3.5-35B-A3B L3 | 与主线并行，单独核查 Attention/MoE 合同 | 同上，不借用 L0 或单个 TopK 测试 |

本片是新的派工/证据导航，不改 `doc/block_checklist.yaml` 的 `to do/ongoing/done`，不关闭整体任务。完整 block RTL 数值验收仍为 **0/5**；固定配置下有效 MAC 利用率 ≥90% 仍未证明。软件 M128 的原观测域 PASS、有限 M1/M2/M3/M17 scripted 端点行为资格与旧 FAIL 均保留，不能互相替代。

## 已实际重发射：真实硬件未被 DPI 替换

新独立 CHIRRTL、SV 任务均自然 exit 0 且完成原锚定清理。独审对两个**新**产物完整流式哈希一次，分别与此前已审产物一致：

| 产物 | 字节 | SHA256 |
|---|---:|---|
| CHIRRTL | 19,551,779 | `bdfbf223cc8c1c8de8a8d21450272878d1422842bc17a452bcef45e9878573bc` |
| SystemVerilog | 48,274,540 | `c117e75ae97fb0a978e7cebe8e942a652bf1fbe927505d66092fa39b87380181` |

重发射使用已合格的 **557 个 class**，不是从当前 main 做全仓 clean build。选定硬件 top 是 `OrderedQkRealMatrixCore`；`OrderedQkRealMatrixCollection` 只是共同 namespace 的生成容器，不能冒充产品 top。现有结构为 38 个定义模块，仍有各 8 个 endpoint/clock-gate 外部声明；发射成功不代表 provider 实现已展开或综合。

尤其要区分：**当前 `OrderedQkRealMatrixCore` 是已限定的 Qwen2 局部结构，不是已经统一五类完整 block 的通用 top。** 本次同 hash 重发射只证明该选定结构可重复生成；还没有五 profile 共用完整 top/interface/RTL hash 的联合验收，不能用文案或五份局部测试替代它。

原算术 provider 保持 8×512=4096 lanes，仍走四个真实 HardFloat 位级模块，不是 scripted tile。13 个原 provider 加边界适配形成 14 文件 canonical 非 DPI 连接：一个 endpoint 仅改名，另一个 wrapper 处理原 22-port 边界；不能把它说成 13 文件完全未改，也不能同时列入两个同名 endpoint。toy/DPI/`m_seqnum` 试验不在此硬件输入链。

**本次新 CHIRRTL 实际仍有四条 W005**：对 Vec(256) 使用 4/5/6/7-bit 动态索引，工具预期 8-bit；本次新 SV 另有一条 `DedupGroupAnnotation` warning。原 0616 审摘要把 CHIRRTL warnings 误列为空，是其过滤漏掉 `[warn]` 格式；现由独立勘误 `3964215f370f9867e99f3786a5dc232a913995aca4416a5ba9b5f1521fdff63b` 纠正，本次与旧 924 B warning log 同 hash。原审 freeze、旧包及历史 warning 保留，不称 warning-free；既有局部 index 范围分析不升级为新完整数值或类型资格。本片不提交大 FIR/SV、class、JAR 或运行缓存。

## current main 的源码来源闭合

本次 source-only 重组绑定 `c590179c4c3424ded9997ba8f15f27821df304c9`，不是把旧 checkout 的 HEAD 当作当前 main。后继 router 小修 `e096dba9220747855223b26d04c2d339c19cb675` 只改三个冷门文件，没有改此硬件源链。

公开 recipe 路径及原字节 pins 在 [来源索引](../candidates/current_hardware_reemission/pins/EVIDENCE_AND_PUBLIC_REFERENCES.json)。从 main 的 preimage/patch 重组 72 源，加原 pins 固定的 20 个外部 HardFloat 源，共 92 源、999,643 B；另重组 6 个 donor provider。独审 fresh hash 98 件均与此前执行输入吻合，共 395 项重组检查。

必须保持以下区别：

- 根 `chisel/` 与 provider 裸文件是 preimage，不等于候选 overlay 已替换根目录。
- 92 源中 60 个有同字节 main blob，其余 32 个依赖公开 recipe 或外部输入；20 个 HardFloat 仍是明确外部前置，不声称整个执行闭包都已放入仓库。
- `replay_handoff.py` 原设计 `exit 2 / INCOMPLETE` 保留；后续 92 源 builder、`qwen2_ordered_vector_chisel/prepare.py` 和 `stage_inputs.py` 的 source-only 成功不把它改成全仓 PASS。
- 新重组树没有再次 scalac；独审也没有重复运行该 recipe、JVM、EDA 或算术目标。

## 资源与硬件验收风险

仅 lane 的 5×FP32 accumulator 与 5×FP32 result FIFO 就有 1,310,720 数据位；service 两个完整 16×256 FP32 tile 另有 262,144 位。两项合计 **至少 1,572,864 数据位**，尚未计 Core 本地存储、score/prob、控制和管线。这是源码容量小计，**不是综合 FF/BRAM/面积报告**，不证明 4096-MAC 配置资源适配。

有界同步 memory 不等于已绑定技术 SRAM；大 `Reg(Vec)` 也不会自动成为 BRAM。局部组合 ready cone 未见自环不等于完整网表 SCC 通过；有意 ICG latch、时钟停启/复位释放、真实 cell mapping、STA/CTS/目标频率 和物理扇出仍待验证。旧 4096 lint、全图 2 GiB RSS FAIL、no-plan 与 CPU 统计覆盖缺口全部保留。

历史 06:54 工具门序（已由文首 Chisel 数值先行顺序覆盖，不再用于当前派工）：后续门按固定原算术、完整 4096 配置及统一通用 top 合同推进：完整 provider 层次的前端/结构检查、综合与闭合 SCC、资源/时序，再做五 profile 的非零完整 block 数值和有效 MAC 周期账本。必须分别记录同一 RTL hash、同一接口及 runtime 配置；不能退回单 512 替代完整验证。本片不把这些待执行门写成通过，也不允许通过缩小 lanes、stub/blackbox 或静默更换算术来“通过”。

## 审核与范围

独立硬件审查：`8159839a9e4e50c41c6b3057601ae1f55be4f67297b04a4d67eb609bddf40cab`；冻结：`e36f413483370372cf5b9a5dbbc30abb1c35ea87e6d7307bb29394262197358b`。安全投影见 [SUMMARY.json](../candidates/current_hardware_reemission/evidence/SUMMARY.json)。采样 RSS 不是连续峰值；root 端点证据为 expected 列表与 source-bound pass，不声称逐项独立 observed digest 轨迹。

本片不含新的四 block 实际成果、共享 state32 修复或 TopK 测试，也不把下一工具候选写成已经通过。后续各自独审后再小批纳入，不等待全部五类同时完工才提交。
