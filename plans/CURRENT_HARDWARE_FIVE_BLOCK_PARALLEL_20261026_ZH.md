# 五类 block：原始 Chisel 完整 M128 数值后再 RTL 回放（2026-10-26）

## 2026-10-29 五profile共享三runtime接线及provider检查点（TEMP / INCOMPLETE）

原selected materializer新增显式共享runtime lease分支：P0使用Qwen2，P1/P2共享原dense14e738，P3/P4共享原MoE42ca970；不是五模型混用一个framework。三实际安装树adoption核原wrapper/Python/固定侧车和完整import-root快照，lease前后验证且postcheck成功后才发布V3；原孤立安装模式仍保留。reference_command、provider算术/程序/完整权重、原BF16/FP32及Torch路由基线不变。

本轮真实provider复用既有已核参考（不是新reference执行）：7阶段native0，overall363.974s、阶段wall合计249.513s。RSS有缺样，内存峰值资格INCOMPLETE，不能将缺样零值或观察最大值当内存PASS/严格上界；原采样/失败证据保留。仅源码、pin、受控摘要发布，shared owner完整路径及runtime/权重/NPZ/生成payload不公开。

此处是runtime物料复用与provider资格，不是DUT数值通过；P0 gate/up仍REQUIRED_UNOBSERVED，五块完整M128 Chisel/最终RTL均0/5，350分钟全链预算/真实DUT速率及80%/90%MAC目标仍未证明。无新workflow/launch/build或采样重跑。 详见[共享runtime来源](../candidates/same_job_materialization_20261029/SHARED_RUNTIME_CN.md)、[adoption受控身份](../candidates/shared_runtime_checkpoint_20261029/ADOPTION_PUBLIC_SUMMARY.json)及[provider实测范围](../candidates/provider_only_measurement_20261029/README_CN.md)。

## 2026-10-29 P0 producer真实来源证据接线（SOURCE_ONLY / INCOMPLETE）

直接修改原producer：在真实host_link前拒绝旧driver .o/.d，仅原stage成功且owned cleanup完成后收集实际GCC -MMD依赖、对象/binary pins和原生receipt；pack创建NEW七文件artifact，保留原source manifest，补入真实compile/constructor/driver来源元数据。P0 consumer从同一artifact自动绑定本次provider程序，按实际选中的header依赖验证split-directory，不再依赖用户手工拼接或同目录猜测。

本次仅源码与metadata轻测，无新build、loader、DUT、workflow或launch。生产证据尚须未来经批准fresh build实际产生；不能回填run40862676969缺失binary或新来源记录。原20→18观察修正不变，gate/up继续REQUIRED_UNOBSERVED/INCOMPLETE；四个其他profile不得使用P0例外。FP32/BF16、Torch路由基线和4096/32硬件不变。完整五块M128 Chisel/最终RTL数值仍0/5，预算/速率及80%/90%有效MAC未闭合。

独立INSTALL_ONLY采样的四阶段均native0，阶段wall合计152.473s，三runtime与cache最终inode去重3,506,537,745B；未执行Torch/reference/DUT。最大process采样间隔12.176789747s（census12.123572151s），观测峰值不是连续峰值或严格上界；三runtime共根不证明五profile复制/参考/输出策略能满足预算。仅提交[受控安装摘要](../candidates/install_only_measurement_20261029/README_CN.md)与提取器，不含运行库、权重或原始进程信息。

详见[producer补丁及证据边界](../candidates/ci_frontend_pipeline_r2_20261029/P0_SOURCE_EVIDENCE_CN.md)。

## 2026-10-29 原物料链到 same-job consumer 接线（TEMP / INCOMPLETE）

新候选将原 selected materializer 的 runtime 安装、所选profile完整权重（五profile合计70张）、独立官方128-token参考及provider路径接到同job V3 consumer；保留V1原件，先核共同build身份与startup ABI receipt，再发布独立V3及消费argv。此处仅发布可复现源码，不替换现有生产入口、不新增workflow/launch、不运行loader、Torch或DUT。

原独立复审41个测试方法及4组phase前置拒绝（P1误带P0字段、SV/driver/source同长度漂移）仅是metadata/control-flow测试，不是五块数值回归。本次便携复测每模式46方法（14连接+6原物料+13 ABI+4存活量+9 runtime）另记，不与历史41相加。真实metadata核70张共3,531,306,272B；本地保留目录存活量不是fresh CI安装/解包/reference/output峰值。P0仍缺实际共享source manifest的12anchors映射、retained消费证据与split-header准入闭包，gate/up继续REQUIRED_UNOBSERVED；完整五块350分钟预算及真实DUT速率未闭合，不压缩硬件/专家/原限制以通过。

同job ABI只约束startup loader/library身份，later dlopen不在资格内。原R2构建binary已随job结束，不从摘要伪造可复用产物。五块原始Chisel/最终RTL完整M128数值均仍0/5，80%/90%目标无新实测。参见[接线候选](../candidates/same_job_materialization_20261029/README_CN.md)与[ABI/存活量账本](../candidates/runtime_abi_liveness_20261029/README_CN.md)。

## 2026-10-29 最新实测：共同 binary 构建通过，完整数值仍 INCOMPLETE 0/5

LOCAL_DATA R2 [run40862676969](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/40862676969) / source `10a30bcf614af2d11ea9aaf3e61469fafd9801dc` / launch `ef6a5fcd95ff643c3d6527f91e4a80e5a1c914a6` 于 11:53:08 UTC 结束 SUCCESS。**PASS 精确范围：固定完整4096 MAC / Vector32 源码重新生成、SV身份、四原生frontend、真实三子库/Host库编译及Host链接、本job内七文件冻结检查；不是 DUT 执行或数值回归。** 27个记录阶段均native0，watchdog reason为空，cleanup/日志EOF完整。没有缩硬件、替换算术或放宽原资源上限。

只上传受控summary artifact `12894603598`，48630B / SHA `dd4d06f325371ff3c9b96fc0ef56e44c43c81dccc7b4745d88b9d6fe61e039cb`。本job报告七文件366163598B，manifest1683B / SHA `6fbc78a408600d17c081f2fde8b70651499b15d3ff26d354b7ae7480475a7374`；**binary/SV/完整manifest与build receipt未上传，binary独立SHA未导出，不能独立重新核验该临时ELF，也不能声称原binary可供五job下载复用**。源码pack执行了ELF64LE和稳定hash检查；该执行结果不等于目前仍持有二进制。原R1失败与其具体文件UNKNOWN记录保留。

下一步只准备经审同一job内数值执行与受控hash/size摘要方案，避免把跨job不可用产物当可恢复输入；不为补hash而重复构建。未来新增摘要字段不得逆推本轮缺失的binary/tool/build-receipt哈希。公开七文件上传仍未获准，无新launch由本checkpoint触发。五块完整M128原始Chisel及最终RTL数值仍 **INCOMPLETE 0/5**；80%/90%利用率目标未变，无有效MAC RTL实测。详见[构建证据与范围](../candidates/build_only_r2_checkpoint_20261029/README_CN.md)。

## 2026-10-29 LOCAL_DATA 构建准入失败及源码修复候选（FAIL / TEMP）

原 run [40856253077](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/40856253077) / source `3185e082df78a59d42d8eb9a76a1afb5146c4e42` 于 10:41:59 UTC 在 `conditional_admission.py:113` 的后端编译准入处失败。22 个已记录阶段均 native0、watchdog reason 为空且 cleanup 完整；本轮重新通过 SV 目录规范身份 `6555ede3…` 和四个原生 frontend。随后 ValueError `previous compiled/dependency product`（36B，SHA `c7300115137928620cfee0cca32dbde94e706eca5d1f2c0734aa80585b99853a`）阻止 archive/link；**没有 C++ archive/link、binary 或数值通过，原 CI 具体 offending 文件未知**。仅摘要 artifact `12890164804`，summary 40969B / SHA `8fab13a8c67f858799980b3e4ac9e6d13baf9a7d783be38c7436e44e72951951`，无 binary/SV 上传。

新源码修正 blanket `.d` 拒绝：仅解析已知 native `__ver.d`/Top `__hierVer.d` 的单行安全 dependency 规则，路径和 prerequisite 绑定已有固定输入，冻结 dependency hash；继续拒绝编译产物、未知 `.d`、recipe/命令/续行/symlink/逃逸路径。保存的真实 native-only Down/层级小样例证明存在合法 `.d`，仅作语法兼容证据，不追认原 CI 文件身份，也不当新完整构建 PASS。新增有界 relative-path/suffix/hash 失败摘要。此提交仅源码及轻测；**不含新启动文件，不重试旧 run**。需后续独立审查新启动身份；公共七文件上传仍未获准，完整五块 M128 数值仍 0/5，硬件/算术/容量/资源上限均不变。

## 2026-10-29 BUILD_ONLY_LOCAL_DATA / NO_PAYLOAD_UPLOAD 范围补充（TEMP）

本轮候选只在单个 CI job 内实际 compile/link 并检查本地七文件；只导出 ≤64 KiB 的受控摘要。binary/SV/driver/完整 source/tool receipts 不上传、不缓存、不文本编码输出，job 临时文件不构成后续五 job 可下载产物。identity 的 artifact_name 仅为本地格式字段，不代表 GitHub artifact 存在；不得据此声称同 binary 跨五 job 回放已具备条件。公共七文件上传仍待用户明确决定，原公共提案保持未激活。源码发布与新唯一 LOCAL_DATA 启动提交仍分开审查；本候选不含启动文件。完整五块 M128 数值仍 0/5，编译成功也不冒数值 PASS。

## 2026-10-29 最新执行导航：frontend R8 已完成；下一步实际 BUILD_ONLY

R8 run [40838373693](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/40838373693) 的21阶段均 native0，完整4096/Vector32共享硬件的源码→IR/SV→真实物理provider frontend仅生成资格通过；**尚无C++完整compile/link、binary或数值执行，五块M128原始Chisel/最终RTL仍0/5**。实际Host峰值RSS9,596,116,992B，说明不能在本地7GiB上限反复重跑。下一步经审NEW BUILD_ONLY沿同源重新生成后，直接条件审查实际Host.mk/85port、冻结derived闭包，顺序编译三子库/Host库并链接同一binary，不再另起frontend-only资格任务。完整实测身份、失败保留、下一步界限见[交接计划](FRONTEND_R8_BUILD_ONLY_HANDOFF_20261029_ZH.md)。原80/90%目标及先模型数值后最终RTL回放顺序不变；本补充不迁移旧PASS或修改74条todo/ongoing/done账本。


## 当前候选补充：共享 Vector/Element 32-lane（2026-10-27）

**这是用户选择的下一候选方向，不是已实现或已验收的新硬件。** 计划为共享 Vector/Element 32-lane、每周期 issue（32 Add + 32 Mul + 32 RNE）；固定完整 4096-MAC Matrix 不变。五 profile 仍必须共用同一份新硬件、同一接口和同一 RTL hash，旧 16-lane 的有限叶级结果不能自动迁移。

- **速率账本不是性能测量。** 32-lane II=1 与 64-lane II=2 都是名义 32 lane-ops/cycle；资源较省只是选择较窄 bank 的设计目标，不是频率、面积或系统吞吐证明。已有纯理想事件模型假设固定延迟、免费输入/输出及无 DDR/其他 owner 冲突，不等同当前硬件执行。
- **必须改完整请求链。** 需要 issue/retire 分离、多 outstanding 的 tag/credit/scoreboard、有限结果缓冲及本地跨 tile cache。当前单 pending owner 不能据名义 II 声称持续发射；缓存槽数须按真实流水延迟、backpressure 与事务语义确定，不把模型中的三槽示例当通用充分条件。
- **算术语义不随位宽规划放宽。** 共享 exact FP32 RNE 流水 Div 需要独立资格，原 sqrt 能力不能删除；各 profile 的逐步 BF16 RNE 和原 FP32 中间值语义分别保留，不能将 Qwen2 FP32 gate/up 压成 Qwen3.5 BF16。统一数据 cache 规划至少 17 B/activation（FP32 gate/up 8 B、两个 FP32 work 8 B、k 1 B），32-lane 每槽数据 544 B；context/tag/flags/scoreboard、DDR ACK 缓冲、Div 流水寄存器及对齐开销另计。旧 13 B/activation 仅属 35B BF16 gate/up 案例，不代表统一五 profile 容量。
- **重新建立完整验收。** 五块可并行，但仍先在原始 Chisel 完成各自完整 M128 数值门，再冻结同份源码及各自输入/权重/官方参考/比较合同，生成并回放同一新 4096 硬件 RTL；不得借用旧 16-lane PASS，或以 leaf、mock、软件模型和理论 lane-ops 替代完整 block 数值与有效 MAC 周期账本。

### 当前代码与失败导航（不升级状态）

公开基线为 `d16001c4543b75455a0cb36a1fcd0908b9aef725`。最近的 [FIFO 模型小批](../candidates/retained_matrix_fifo_model/README_ZH.md) 只发布原字节候选、类型身份和历史严格 hash/form FAIL；它未给出 FIFO 24-edge 等价或 service 加速资格。[service 阶段观测](../candidates/retained_matrix_service_observation/README_ZH.md) 仍为 CPU120 FAIL、0/1 case：首个 reset-high `step(2)` 返回不证明后续 `step(3)` 已进入或完成，也不能定位热点。后继 formcheck 或修复门须绑定自身实际证据，不能回填旧发布范围。

norm 父链本轮 3/4 是三个协议 case（unsupported/held-memory-abort 与 DDR epoch late-reply 隔离）的局部通过；fullcontext/txn0 探针失败，整体仍 FAIL，不是 norm 数值、完整父链或真实 Admission 集成 PASS。txn0 Boundary 的统一合同修复候选尚待真实独立验收，不凭源码修改或编译成功升级。

本增补仅更新中文候选与派工导航，`doc/block_checklist.yaml` 的 74 条任务及 13 done / 14 ongoing / 47 to do 全部保持，历史证据与 FAIL/TEMP 不删改。完整五块 Chisel/RTL 联合数值资格仍未建立，完整 block RTL 仍 0/5，4096 有效 MAC ≥90% 未证明。下文各日期、当前字样和旧基线保留为历史时点说明；原始 Chisel 数值优先的顺序继续有效。

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
