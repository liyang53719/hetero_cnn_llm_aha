# 三模型五类block：本轮计划与检查表

更新：2026-10-17 08:44 UTC。只新增状态快照，不覆盖冻结计划、源码或历史回执。
最终目标仍为同一固定配置/输入的完整实际RTL数值与状态PASS，以及
useful MAC / (4096 MAC每拍 × 完整block wall cycles) ≥90%；固定资源不能
按活跃lane缩小，DMA、stall、阶段间隙及最终写ACK均计入wall。
batch1/M128继续推进；1024/1224长序列待用户选择，不阻塞M128。

## 五类block状态

状态指完整业务接入/验收，历史组件或软件smoke不自动升级为当前完整block通过。

|目标|状态|当前真实边界与下一门|
|---|---|---|
|Qwen2-1.5B典型block，当前L0|ongoing；M128模型指定门禁done|2e591b6同host完整M128的27项assigned官方门禁与固定算术通过，21 completion/17 owner作业；全29节点、逐阶段参考内容身份固化、完整Chisel/RTL与90%仍待完成。旧超时/失联历史保留。|
|Qwen3.5-0.8B L0，GDN+dense|ongoing，本轮未变|历史真实payload与合成输入cold/carried/decode软件smoke保留；当前完整M128原业务/RTL资格不继承。|
|Qwen3.5-0.8B L3，Attention+dense|ongoing，本轮未变|历史真实payload、合成M128软件数值及组件工作保留；当前完整原业务/RTL资格不继承。|
|Qwen3.5-35B-A3B L0，GDN+MoE|to do，当前完整block|保留既有config/header/几何合同；真实payload、route/状态、完整数值与RTL/性能尚待闭合。|
|Qwen3.5-35B-A3B L3，Attention+MoE|to do，当前完整block|同上；必须使用真实路由与tile映射，不把Qwen2或0.8B结果迁移为PASS。|

按完整block M128模型指定27门禁口径为1/5；全29节点、完整RTL与利用率最终验收仍未完成，五类最终目标均非done。范围来自[统一目标计划](three_model_typical_block_closure_20260917_zh.yaml)；
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
  该微测不是完整Public数值PASS；其`full_public_admission=false`。后续有界owner故障验证见下。
  packed M128全启用FMA预期260,308,992，不能用selected-cell模型25,362,432替代。
- **done：SFU源审计及单上下文数值/边沿候选。** [审计](../candidates/qwen2_resident_matrix/sfu_microsequence_audit/README_CN.md)、
  [候选与资源账本](../candidates/qwen2_resident_matrix/sfu_silu_cycle_candidate/README_CN.md)：
  原16 divider/options0正常输入最少25拍；71,680个SiLU vector至少1,792,000拍。
  即使其余工作完美重叠，固定useful=6,014,828,544下上限81.9455%，故当前配置90%不可能。
  options16虽为14拍，但新增递推逻辑/时序成本，默认关闭；软件callback并非divider RTL等价。
- **done：原始业务be00失败诊断与归档；完整业务仍未通过。** 原始285源/12生成变体未热替换。
  原运行总2762.816418秒，实际内层2400.210057941秒，在FFN PC16触发原有deadline。
  完成PC0–15，Attention已推进；未完成完整数值比较/postflight。
  [原始安全回执与失败计划](U00_2_PUBLIC_M128_CLOUD_BUDGET_FAILURE_20261016_CN.md)保留原身份；不扩大预算盲目重跑。
- **done：实际PublicKvTransport的M1/M2有界接入。**
  [证据](../candidates/qwen2_resident_matrix/attention_packed_public_evidence/README.md)：原owner、K/V和scratch共享一次parent tick，
  输出与score逐位匹配原Fraction参考；四个故障场景失败并排空。不是完整M16/M128 block。
- **done：A复用有界控制/算术及Chisel前端资格。**
  [数值候选](../candidates/qwen2_resident_matrix/dense_a_hold_numeric/README_CN.md)5组开关对比累计6,553,600次C++ FP32 FMA，
  全输出及4096-cell终态逐位一致；M128项仅K32/N160。
  [实际Chisel前端](U00_2_DENSE_A_HOLD_FRONTEND_20261016_CN.md)四配置编译/CHIRRTL通过，CI38973350757总24.819秒；
  32个1R1W bank不变，Queue4→3，新增2048bit hold及78bit控制。尚无硬件协议执行、RTL、面积或时序验收。

- **done：完整M16原Public链的27个assigned官方门限。**
  [原始证据与边界](U00_2_PACKED_M16_ASSIGNED_GATES_20261016_CN.md)：首次Host请求类型错误的失败已独立保留，严格绑定实际PrefixJob后，
  新运行21个完成、17个owner任务、10字段完整，固定算术逐位通过；总591.280260秒，实际数值569.456837秒，316源postflight。
  状态严格为PASS_ASSIGNED_OFFICIAL_OBSERVED_GATES_ONLY；全29节点、M128、RTL及90%仍false。
  M16已执行1,462,272个Dense物理step，不得把总软件耗时简单乘8当M128预测。

- **done：实际原生算术的分块M17/M32 Public transport组件。**
  [冻结证据](../candidates/qwen2_resident_matrix/attention_packed_tiled_evidence/README.md)：
  M17成功、panel abort与DDR错误三项共34.360秒；M32成功60.436秒。
  所有score/output与独立Fraction参考逐位一致，启用物理FMA分别7,704,576与21,037,056。
  query16/key16跨tile时保持PV累加器和七条真实raw response ACK停顿边；187源与ELF前后不变。
  仅组件资格，未运行完整M128程序，软件边沿不能作为RTL周期。
- **done：分块10字段observer冷资格与实际M17算术捕获。**
  [独立准备](../candidates/qwen2_resident_matrix/attention_packed_tiled_observation/README.md)31项normal通过；
  优化模式23项通过、8项明确跳过live monitoring，生产入口拒绝-O。
  另行执行的[M17捕获](U00_2_TILED_M17_OBSERVER_CAPTURE_20261016_CN.md)总19.780646秒，10字段因果覆盖完整；其中output/score逐位参考比较，其余8字段仅捕获完整性。候选传输与捕获9.899768秒、Fraction参考9.013515秒分开记录。
- **done：M16预算依据提取。** [实测与源推导](U00_2_PACKED_M16_BUDGET_BASIS_20261016_CN.md)
  固定Dense工作量与B流量不随M16到M128增长8倍；A ingress及部分逐行工作增长。
  未分配的341.233秒不能全部归于Attention或FFN；M128在原2400秒预算内的可行性尚待实测。

- **ongoing：完整M128入口修复；首个冻结尝试已失败保留。**
  [资产准入](../candidates/qwen2_resident_matrix/attention_packed_m128_assets/README.md)、
  [入口](../candidates/qwen2_resident_matrix/attention_packed_m128_entry/README.md)、
  [有界执行](../candidates/qwen2_resident_matrix/attention_packed_m128_run/README.md)保留原M128输入、两套参考与native128身份。
  346源compact digest f5e1dcdecc406750cd6409e45a97184294ba94d4e61cb9ef67d53641fd912104；
  wrapper582833958e1dda4772f3e23c02f2ec0a17be9d6d7e5e3e5fba36618fb4ca8f30。
  启动前修复隔离Python父进程的兄弟模块导入错误，原未执行版本9926保留，无失败数值任务冒充重跑。
  已完成32+32资产/入口与76+76执行控制冷测，但它们未覆盖实际run函数中的独立raw-KV M16门禁。实际attempt在进入数值调用后31.690888秒以child/outer exit1退出，cleanup完成；没有算术或数值比较结果。[原始失败归档](U00_2_PACKED_M128_ADMISSION_FAILURE_20261017_CN.md)保留真实终态；失败原346源保持不变，新候选需逐项审核全部准入并执行到首个native边界的冷回归。尚无本次M128 PASS或RTL结论。

- **done：严格M128 run准入窄修复；ongoing：新尝试终态追踪。**
  [独立修复](../candidates/qwen2_resident_matrix/attention_packed_m128_run_gate/README.md)仅修改独立raw行数门禁和诊断，保留真实snapshot/M16前提/参考/源码检查。
  实际entry.run穿过真实verify_snapshot到第二runtime调用的pre-work哨兵；13项精确原因拒绝测试通过，无数值工作。root2+2及独立2+2冷测试通过。
  后继wrapper cf20ec20ed2f023bf1d9b2b2f10ecd4d7963699cebab5f984e3a429e8f3ed9eb，350源compact map
  4e0f86922cdc268f245aa0105e03fbae617add5da8b3609e3799b12ca72943b8；83+83冷测通过，原2400/2424/2430预算不变。
  实际00:11:06启动，PC0–9前缀完成79.216911秒；00:25原工具会话不可恢复，磁盘无终态回执。
  当前执行连续性未确认。不把阶段报告当完整数值PASS，不据会话丢失推断数值FAIL，也不重复启动可能仍在运行的任务。先核实存活和原始截止时间，保留不完整证据。

- **done：默认关闭packed stream client源级候选与冷资格。**
  [候选](../candidates/qwen2_resident_matrix/attention_packed_stream/README.md)复用原MatrixStreamPort与两槽结果FIFO，
  新增53个显式控制bit，无operand/result复制寄存器；原metadata队列导出可选排空状态，暂停不丢PV累加context。
  修复组合endpoint的seed ABI闭包及held completion晚abort，同边沿done/错误不丢债；19+19冷测及独立源评审通过。
  本候选的组合18源切片已通过Scala class编译，见后文；尚无elaboration、RTL或完整数值验证，mode0 owner、raw/scratch、panel384B及scalar接线仍待完成。
- **done：原始准入探针与中断证据归档。**
  [准入回执](../candidates/qwen2_resident_matrix/attention_packed_m128_admission_evidence/README.md)真实PROBE/350源逐字节核验，2+2测试零跳过。
  [执行连续性记录](../candidates/qwen2_resident_matrix/attention_packed_m128_continuity_checkpoint/README.md)保留00:32:18时的原始prefix/progress及缺失终态事实；20+20冷测与独立复核通过。
  进程存活、退出码、清理和完整数值结果为unknown/null；不伪造失败或超时。原约00:51:36截止时间过去也不等于已证明清理。
  后续研究可持久查询的云端job及独立consumer profile，不能绕过原CPU/backend门禁或转用用户本地机器。

- **done：默认关闭raw scratch源级补丁。**
  [源与边界](../candidates/qwen2_resident_matrix/attention_raw_scratch/README.md)在原13bit line上严格扩展请求/ACK到4096..4191，复用word512..523共6KiB原银行，不增加SRAM。
  独立generation/query/head与96bit written-valid，clean匹配ACK后发布，abort后保留已接受身份排空。增量177控制bit；15+15冷测及独立源审查通过。
  相同上下文tag不可在可能有延迟/重复ACK时复用；本补丁不宣称能区分完全相同的旧key重放。kernel/owner接入与实际RTL仍未完成。
- **done：新切片Scala class编译资格；硬件展开待办。** 精确恢复87个原lock JAR（61,870,159B），未上传依赖。
  首次17源编译6.810446秒以exit1结束且清理完成，原因是闭包缺少已有MatrixAccumulatorSeedController类型；不记编译PASS。
  独立18源后继加入真实原控制器、保留17源和工具链，root与独立12+12冷测通过；2026-10-17 01:08 UTC实际编译14.483935秒成功，compiler/outer exit0且cleanup完成，129个class哈希核验。
  [复现与原始失败/成功证据](../candidates/qwen2_resident_matrix/attention_scala_compile_evidence/README.md)经root4+4与独立4+4零跳过复核。只提交源码、87项官方依赖lock引用和hash；不提交class/JAR。没有调用emitter、生成RTL或运行数值任务。
- **blocked：原M128完整执行结果恢复。** [截止后只读观察](../candidates/qwen2_resident_matrix/attention_packed_m128_continuity_checkpoint/deadline_observation/README_CN.md)记录00:52:04仍只有同一前缀和四项终态缺失。
  原deadline已过，但退出、清理、完整数值结果仍unknown；不在旧环境盲目重跑。首个tiny consumer CI已完成源审查和root/独立21+21冷测；114项输入源码与公开bf1c7d3逐字节一致。首次workflow在公开6f12457触发run38990565055，于01:22:19 UTC失败，jobs=0，尚未执行算术。root/独立PyYAML均复现第36行139列的未引用冒号解析错误；服务端annotation未取得，不能伪称已读。独立窄修复改为literal block，原shell命令不变，4+4真实解析回归与21+21原控制冷测通过；修复后4538a10触发run38991969943，于01:42:33 UTC完成SUCCESS；安全产物下载及SHA核验完成，见实际资格归档。
- **ongoing：持久云端小规模算术消费者资格。** [固定入口](../candidates/qwen2_resident_matrix/portable_consumer_qualification/input-contract.json)与独立workflow保持原4源算术构建、profile2固定小case和实际ScalarService测试；不下载权重、不运行参考生产或完整block。使用官方PyPI固定NumPy2.3.5，工作150秒/内部清理159秒/终态160秒，外部TERM150/KILL+10；job10分钟含准备与安全摘要上传。仅保存三项固定名称摘要14天。新consumer身份与历史producer明确分开，不放宽原M128 CPU/backend门禁，不继承旧M16/native资格。

- **done：默认关闭的原owner QK单key final-only源级接线。** [真实补丁与边界](../candidates/qwen2_resident_matrix/attention_qk_owner_route/README.md)修改原Qwen2ContinuousBlock/QwenOwnerKernel，接同一Matrix服务，8深度step以真实接受推进，保留结果槽至原fold/scale/score提交后再ACK并等待done。
  修正packed接受误采legacy错误、异步错误丢DDR/local/scalar债务及locked重复发布；root15+15和独立15+15冷测通过。38新增owner控制bit+既有client53，共91，无新payload。单key桥接当前8slice物理issue成本更高，不作为利用率优化；真实16-key packing、raw scratch、PV6和panel384B仍待接线。独立完整83源闭包已实际class编译通过，见下文；尚未展开或数值执行。

- **done：真实QK owner完整依赖class编译。** [复现与安全回执](../candidates/qwen2_resident_matrix/attention_qk_owner_compile_evidence/README.md)包含原完整项目和20项固定HardFloat源码，共83源，复用87个已固定JAR。真实编译28.262122秒、compiler/outer exit0、cleanup完成，474class哈希与全部输入前后核验。
  root13+13及独立13+13执行前冷测；原件支撑root4+4、独立4+4零跳过归档验证。90秒work/TERM90/KILL+10外包络；没有调用任何emitter、elaboration或数值任务，class/JAR/归档payload不上传。

- **done：新云端固定算术消费者实测资格。** [实际产物与验证器](../candidates/qwen2_resident_matrix/portable_consumer_qualification/actual_4538a10_20261017/README_CN.md)保存run38991969943的三项原始JSON、冻结契约及安全摘要。PASS_FIXED_ACTUAL_CASES，构建/检查6.229秒，Python3.12.15/NumPy2.3.5/GCC13.3，实际共同CPU flags有AVX2、无AVX512/AMX。
  QK/PV/PV128步数边界、7个原Scalar及2成功/3故障SiLU向量通过；root与独立19+19归档冷测通过。尚无新producer、完整PublicM16/M128、selected故障时序、RTL或90%资格，旧生产环境门禁不放宽。
- **done：默认关闭真实16-key QK馈送源级候选。** [原owner补丁](../candidates/qwen2_resident_matrix/attention_qk16_owner_route/README.md)复用原denseWeights[256]/av[16]/acc[16]，逐深度采集至多16个实际K包，尾列显式置零；最终结果按原次序逐key折叠/scale/写score，最后一个score提交才ACK FIFO，matching done前不改base。
  新增8控制bit、2状态，无新payload；root12+12与独立12+12冷测通过。M128源推导QK issue55296、K traffic792576 DDR beats、fold1585152 Adds，仍不是周期或RTL利用率证据。该后继已实际class编译通过，尚未展开或数值验收；PV6/raw scratch仍待接入。
- **done：QK16真实83源class编译。** [最小差分证据](../candidates/qwen2_resident_matrix/attention_qk16_compile_evidence/README.md)记录29.234551秒、compiler/outer exit0、cleanup完成，83源/87JAR/474class核验；相对前次只变2源和3class哈希。root及独立15+15执行前冷测、原件归档root4+4和独立4+4零跳过通过。复用前次repro/launcher基线，未上传class/JAR，无RTL或数值结论。

- **done：独立新环境producer/launcher/完整M16接入源码冷资格；ongoing：同job实际运行编排。** [producer](../candidates/qwen2_resident_matrix/portable_official_producer/DRIVER.md)、[有界准备阶段](../candidates/qwen2_resident_matrix/portable_official_producer_launch/README.md)、[完整M16入口](../candidates/qwen2_resident_matrix/attention_packed_m16_same_host/README.md)共5+11+12文件已冻结复核。
  producer保留原native_forward、29阶段/116exports与两套C++独立参考，66依赖补齐；root21+21冷测通过。准备launcher保留真实owned child退出/组清理与独立原数组复验，固定官方包wheel/hash，890/899/900共享预算；root44+44冷测通过。完整M16入口保持27assigned数值门限、wholephase与ACK/晚参考围栏不变，root36+36通过。
  357源预构造绑定8337840只作为源码preflight，实际运行必须使用新触发commit重新生成SOURCE_CONTRACT/fullmap。尚未安装新生产环境、下载权重或运行producer/完整M16/M128；独立组合900准备+930完整M16同job父进程/workflow仍待审查，不启动孤立producer以免丢失同host资格。
  02:07云端执行环境故障，02:13恢复且工作目录/草稿仍在；已重核源码和冷测，未确认文件丢失。原M128失联状态不因此改为通过。

- **ongoing：新同job参考生产→完整M16数值任务。** [同host组合入口](../candidates/qwen2_resident_matrix/portable_same_host_m16_launch/README.md)及独立push-only workflow已完成root/独立45+22+10两模式冷测、真实Git worktree/357源动态commit构造和隔离入口pre-work验证。
  最后隔离verifier probe发现原launcher漏importlib.machinery；已作一行显式import后继并重新绑定源码锁，原027历史版本不覆盖。未用调用者隐式预加载冒充跨exec修复。
  本提交发布单次触发workflow：同job固定Python3.12.15，重新安装固定官方依赖、重跑tiny、生成新官方M16/两套C++参考，独立复验原数组后运行完整M16。producer阶段内部890/899/900共享截止，完整M16内部900数值/930外层；组合外部TERM1940/KILL+10，job40分钟含准备/安全产物。没有独立producer-only外部900秒watchdog，不能称为每阶段外部硬限。
  只上传固定安全摘要/hash/身份，不上传权重/tensor/npz；运行结果尚待实际CI回执，所有新producer/完整M16/M128/RTL90验收在终态前保持false。失败先保留原run和诊断，不同identity重新构建才可另行重试。

- **done：首次同host启动源码缺失诊断；ongoing：完整发布闭包修复后的独立尝试。** run38997454218/job117293011043在96b0548于03:05:50 UTC源码preflight失败，缺portable_official_producer/gate.py；未建工作输出，无产物，未安装包/下载权重/执行producer或完整M16。
  [安全失败与完整发布审计](../reports/execution/QWEN2_SAME_HOST_M16_PUBLICATION_REPAIR_20261017/FAILURE.json)绑定原log hash；84个非递归Git树经Merkle核验，379项中378精确匹配、仅gate缺失，无其他内容/mode/size错误。之前本地组合含未发布文件，不能代表实际远端完整性。
  窄修复只补原已复核gate、给workflow加一次修订注释并更新其契约hash；parent45+45、worker22+22、workflow10+10冷测通过。新增[发布闭包工具](../tools/publication_closure/README.md)，root和独立36+36原件回归通过；真实候选commit/tree必须完整379项PASS才移动main。旧运行不重跑、不覆盖，修复后为新commit一次尝试，数值验收仍待终态。

- **done：第二次同host尝试真实失败回执；ongoing：限量诊断后继。** run38998662188/job117296723295在902680a上完成checkout、private venv、固定bootstrap/runtime安装、installed inventory及fresh fixed cases；fresh producer子进程exit1。总55.409526秒，所有已拥有进程组清理完成，producer未资格通过，完整M16未启动。
  [安全失败摘要及诊断边界](../reports/execution/QWEN2_SAME_HOST_M16_DIAGNOSTIC_SUCCESSOR_20261017/README.md)保留4原始JSON和ZIP hash；旧产物缺少子进程内部异常位置，不能从父级ValueError推断根因。真实冷CLI已到首次fetch_range入口，未发网络请求；该检查不能证明hosted实际失败点。
  后继不改driver/算术/数值门禁/预算，只在失败且清理完成后从私有日志最多读取65536字节，输出allowlist异常类型和固定源码路径/行号；不输出原始消息、URL、locals或张量，不扩大artifact名单。低于2秒余量跳过，诊断最多1秒并保留至少1秒旧回执窗口；无法解析则UNAVAILABLE。诊断观察不是认证根因或验收证据。
  root及独立143+143冷测试通过；新381文件实际Git发布闭包须PASS后才触发一次诊断尝试。原运行与原始未知状态保留，不填造新producer/M16/M128/RTL结果。

- **done：诊断尝试定位参考命令边界和修复目录契约。** run39000095742在af3d9d3上74.110056秒失败且清理完成。安全诊断观察到driver.py:557→425及owned_commands.py:101的ValueError，定位到C++参考owned调用；没有nested stderr，不把观察当认证根因，也不从调用栈推定前序生产资格。
  [源证明与安全回执](../reports/execution/QWEN2_SAME_HOST_M16_REFERENCE_DIRECTORY_FIX_20261017/README.md)核对原builder.py:223明确要求预建raw_stages，原RMS/ROPE wrapper也在启动前创建；新driver遗漏。两套原生成C++打开首个输出文件失败时exit1，不会自行创建目录。
  唯一生产逻辑修改为每个reference角色在不变命令之前exclusive raw.mkdir(mode=0o700)，原数值来源/算术/预算/接受门限不变；测试覆盖两角色及目录/文件/符号链接冲突。root和独立166+166冷测、三隔离入口与357源worktree验证通过。新381项实际候选Git闭包PASS后触发一次修复尝试，旧实际失败保留，完整M16/M128/RTL仍未通过。

- **done：新host M16参考生产实际资格；blocked：完整M16子进程失败点缺失。** [四项原始安全JSON与hash](../reports/execution/QWEN2_SAME_HOST_M16_FULL_FAILURE_DIAGNOSTIC_20261017/README.md)保留run39001176206/artifact12088928570、ZIP aefc23d3fa9f4cd766f60f156140a0b10d8685a9cc815cc49599ad3b075ee3f4。
  producer_summary为PASS_FRESH_M16_PRODUCER，76.564196秒，8个setup/producer/独立native验证阶段均exit0清理完成；worktree/compose/seal也完成。随后full_m16子进程exit1，整体1004.057939秒，所有已拥有进程组清理完成。新完整M16/全29/M128/RTL均未通过。无full_m16_summary产物，不能据耗时认定超时或数值差异。
  后继只在失败且已观察退出/清理后，读取原有私有actual/summary及控制元数据和受限源码栈，投影固定status/有界completedPC计数/elapsed等，不导出原异常消息、地址、张量或数组，也不改原算术循环/门限/预算。诊断在旧绝对终态计时内合作限1秒、保留回执余量；缺失/异常则UNKNOWN且所有acceptancefalse。
  root200+200与独立冷测试/隐私检查通过。5个runtime后继文件和6个安全归档文件独立冻结，新383项实际Git闭包PASS后再触发一次带失败进度的数值尝试；原M128失联状态不变。真正128-token组件源级冷资格在并行准备，整体M128尚未运行。


- **done：新host完整M16执行到21条命令；ongoing：写入格式契约修复后的终态验收。** run39003509172在46f5766上整体744.020100秒退出失败且清理完成；fresh producer资格通过。受限诊断记录PC0–20、21次完成、17个owner作业，数值643.242548秒，内部状态PASS_REDUCED_BF16_OBSERVED_OFFICIAL_GATES。独立terminal尚未调用，完整M16 acceptance仍false，不能将诊断标签升级为通过。
  [原始安全回执与修复依据](../reports/execution/QWEN2_SAME_HOST_M16_WRITER_CONTRACT_FIX_20261017/README.md)保留artifact12090039191与ZIP962e63e2cf700414149441a172334c606e21e2df04195389ba6df04c5193b0cc。源码确认validated_policy_jobs使用整数PC键；JSON读取后变成字符串，入口再次sort_keys编码令2/10排序改变，导致返回值与磁盘误判。窄修复保留有界严格JSON读取，改按原original.encoded写入器逐字节核对；原数值、terminal、postflight与900/930秒预算不变。
  仅四个runtime文件变化：entry、回归测试、输入hash与workflow修订注释。root252+252冷测、独立52+52入口及原terminal回归、357源真实worktree组合通过。新383项实际Git闭包须通过后才触发一次新运行。较早4f失败仍为原因未知；M128同类入口修复单独冻结，a959未发布候选禁止推进main。五block完整M128与RTL仍0/5，80%/90%利用率无新增实测。


- **done：6cc 新尝试真实超时证据；ongoing：模型执行开销定位。** run39005243171/job117316258340在6cc2003上失败，artifact12090687791，ZIP37a514320a3337673406b2c4feac667a1815b8373cf626689d090659798e57b8。fresh producer84.792876秒资格通过，整体1011.004021秒，所有已拥有进程组清理完成。数值900.232086秒，完成PC0–18、PC19已派发但尚未退休；原execute_numeric.py:109累计900秒deadline在Down触发，写入比较和终态门禁尚未到达。不能记录完整M16通过。
  [精确四JSON及源码证明](../reports/execution/QWEN2_SAME_HOST_M16_PC19_TIMEOUT_20261017/README.md)保留旧证据；执行356静态源与8个栈帧逐项匹配。与46f相比仅entry/test改变，热点源码相同；前缀36.98→57.50秒，速度波动原因未知，CPU affinity不能证明CPU型号、争用或限频。暂不加预算、不盲目重跑，先做纯控制开销的等价性和局部测量。
- **done：M128 源码检查点；to do：实际M128运行。** 保存修正后的22个入口/35个支持/7个producer文件与7个parent文件；root490+490冷测、独立238+238及隔离边界/420源worktree组合通过。当前检查点明确不发布新的M128 workflow，已有M16 YAML原样不变，不触发额外数值CI。对应454项实际发布源闭包须核验；此前含workflow的209603d候选保持未发布。未来运行必须同一job重新生成参考并通过完整M16原terminal及same-ELF先决，再执行真实M128，不能拿本次源码门禁或旧诊断PASS替代。完整五block M128/RTL仍0/5。


- **done：纯控制重复读取优化及父级耗时观测；ongoing：同预算完整M16实跑复验。** 保留原历史源码，通过精确hash守卫在composition末端应用一行变换：ordinary_edge仅在job admission读取此前非admission也无条件读取的ports。每个owner/Host tick、pre/post reset、deadline、计数、握手、ACK、数值运算与terminal保持不变；原entry写入比较修复继续保留。
  [源级/局部控制证据](../reports/execution/QWEN2_M16_CONTROL_PORTS_TIMING_20261017/README.md)中22+22差分用例、完整301+301冷测、3隔离边界和359源真实worktree组合通过。root对严格源码缓冲加载的真实Down控制路径执行4对AB/BA有界样本，使用明确无算术功能的Python ABI；3421条边沿、packet/traffic、ACK与terminal相同，wall中位0.251672→0.215704秒，配对比0.85342，CPU配对比0.85312。此局部结果不能证明完整M16速度、900秒余量或硬件利用率。
  父级仅在owned phase边界采样wall和RUSAGE_CHILDREN，退出/清理后才输出有界诊断；沿原绝对cleanup deadline重新启用alarm，失败保留UNKNOWN/UNAVAILABLE，去掉可选CPU型号读取。它记录已回收子进程CPU，不等于独占CPU时间或限频证明，不改原900数值/930外层预算。
  10个runtime/source后继与3个安全证据独立冻结，386项实际Git发布闭包须PASS后才触发一次新M16尝试。M128已保存检查点引用旧M16源，必须另行重绑定并完成同job先决后才可启动；本提交不发布M128 workflow。完整M128/RTL及90%利用率仍未通过。


- **done：bf29 新host完整M16指定27数值门禁实际通过；限定清理保证待修复。** run39008436816/job117325592334于2026-10-17 06:11:41 UTC成功；artifact12091514715，ZIP5169209a5f580e51f0785ef81e6a25577dca47dd7318d17b0e6dd60675741969。总534.732416秒，完整M16阶段466.928041秒；原terminal报告27个assigned门禁、28个observed stage、21次completion、17个owner作业与固定算术通过。直接子进程exit0，实际359源manifest与385raw/358静态映射和当前commit逐项一致。
  [五份原始安全JSON及限定归档](../reports/execution/QWEN2_SAME_HOST_M16_ASSIGNED27_PASS_20261017/README.md)保留原字节；原产物中的cleanup=true只是当时helper报告的清理完成，不能证明所有后代均已退出。独立离线检查核对回执/源码/nonce/CHILD_RESULT摘要，不重放私有数组。原27数值证据保留，完整29/M128/RTL验收仍false；本次耗时改善不全归因于单行优化。
- **blocked：严格进程组清理确认；ongoing：生产helper修复。** 新有身份记录的生命周期测试发现，同一后代在helper返回后仍处于R调度状态，约21ms后消失；R不证明SIGKILL后继续执行应用指令，但明确说明当时尚未观察到全组退出。较早只记录PID存在的失败原因仍UNKNOWN，不能用本次结果追溯填造。
  源码确认旧cleanup_owned只发SIGKILL并等待直接leader，finish_owned立即返回True，后续caller可能据此读写产物/发布成功。测试侧增加等待不能修复生产保证。启动M128暂缓：需在原绝对stop内、保持leader未reap以固定group身份，完成全部同组非leader退出确认后才reap并发布成功；扫描不完整/身份不明/超时必须fail-closed，禁止下一阶段，不能在reap后向裸PGID发信号。现有数值预算不扩大，不将清理问题表述为用户取消。


- **done：严格进程组清理源码与真实生命周期资格；ongoing：首个完整M16→M128同job验收。** 新source-bound strict helper在保持直接leader未reap和身份匹配时发送SIGKILL，在原绝对stop内完成两次有界全组扫描，所有非leader身份（含Z/X）均不存在后才reap leader并签发父级proof。扫描不完整、身份异常或预算到期均fail-closed；失败保留cleanup=false并禁止下一阶段。可在原剩余时间内或非阻塞方式回收直接handle，但显式记录authority释放，禁止reap后的裸PGID信号。
  两个活跃调用边界launch.finish_owned/owned_commands都要求同一owner/stop/source的严格proof才允许cleanup=true。覆盖显式owned组及外层handoff；同组内部普通同步subprocess仍按原工具契约执行，不宣称每个内部阶段均有全组退出屏障。原独立tiny历史入口不改变，当前tiny worker由外层严格stage覆盖。
  [有界源码/生命周期证据](../reports/execution/QWEN2_STRICT_OWNED_GROUP_COLD_20261017/README.md)：独立43+43 helper测试及root一次normal/-O共6个真实zero/nonzero/timeout生命周期通过；原首轮捕获R状态后等待空扫描再reap，返回后扫描为空。root与作者完整638+638冷矩阵通过，463源无漂移，真实424源worktree组合通过。旧golden-pin冷测失败和历史清理缺陷均保留，不用后续PASS改写旧结果。
  26个非workflow源文件＋仅新M128 workflow＋3安全证据独立冻结；463输入及安全证据须在实际候选Git闭包核验。原M16 YAML字节不变，避免单独重复M16作业。新job重新生产参考、完整M16原27门禁/终态/strict cleanup通过后才进入真实M128；同ELF和当前job来源绑定不放松。预算仍M16数值900/外层930，M128数值2400/外层2430，组合外部TERM4910/KILL+10。发布触发一次独立尝试，不承诺运行通过；完整M128、全29、RTL与80%/90%实测目标继续保留。


- **ongoing：原Chisel prefill连接；done：QK-only BF16边界片段的源码/类编译。** [源码连接审计](QWEN2_PACKED_PREFILL_CHISEL_CONNECTION_AUDIT_20261017_CN.md)确认原Qwen2ContinuousBlock已支持maxTokens<=1024和因果token/key/head控制，StreamingDense已有多行prefill。HostBlockTop的另一路Qwen3.5 H1024 M1 profile限制不是此Qwen2 packed路径或官方上游整体限制。
  真实已编译QK16候选缺少模型要求的completed-dot及scaled-score BF16-RNE物化；完整official_bf16 policy又有maxTokens==1024及RMS/owner ABI变更，不能直接与packed<=128叠加。[新增默认关闭QK片段](../candidates/qwen2_resident_matrix/attention_qk16_bf16_materialize/README.md)复用F32.bf，仅在最终16-lane fold和scaled-score两个边界物化，score SRAM与max共同消费rounded值；非有限结果走原poison/drain。不增加状态/寄存器/存储/端口，默认路径保留。
  可移植源码/数学参考11+11测试通过（含195840个midpoint邻域），独立复核通过；同一候选83源Scala class编译exit0、474类、29.4417秒。没有elaboration/CHIRRTL/RTL/硬件协议/完整block数值通过。原编译清理观测仅killpg(pid,0)得ESRCH，不是全后代消失证明。
  此片段仍为core-only，尚未Host/kernel透传；raw scratch、六head控制、384B panel、PV供数/暂停保持及最终债务fence仍须集成，Scalar underflow与NaN异常策略未整体对齐。当前新文件与运行中的463输入集合无交集，M128 workflow字节不变，运行39012470402继续沿原commit进行；不得把并行源码修复当作该运行已通过或RTL等价。


- **done：Qwen2 L0完整M128模型指定27门禁实际通过；ongoing：同刺激RTL所需内容身份固化。** [七份原始安全JSON与证据](../reports/execution/QWEN2_SAME_HOST_M128_ASSIGNED27_PASS_20261017/README.md)绑定commit2e591b6df29fc08504dca264264b149c27e2cf95、run39012470402/job117337723540、artifact12093963949，ZIPf106bdb2820da5f850a17288496613b6bea3b96b414576d36e03a681b529eb62。job于07:44:30 UTC成功；同job先通过M16，484.610557秒，随后M128阶段1570.271008秒，整个流程2191.158995秒。M128 rows128、27assigned/28observed、21completion、17ownerjobs、fixed arithmetic通过；直接child exit0，各暴露阶段strict-cleanup成功回执成立，全29/hardware/RTL仍false。
  root与独立审查复验7原始JSON、463源/462raw pins、真实commit动态361/424源manifest、两份可重建CHILD_RESULT摘要、共享nonce及M16 prerequisite/producer资格指针一致；归档24+24拒绝测试通过。严格清理由已绑定源码强制执行，但原始扫描proof未上传，不能把离线回执核验说成再次运行私有数组或清理实验。
  同刺激回放的内容身份仍有具体缺口：公开源码可恢复Qwen2-1.5B-Instruct revision ba1cf1846d7df0a0591d6c00649f57e798519da8、token/position0..127、past0及input FP32 SHA ddcdcca67cb3e26007880a78074ea3eb70bf83e8d8060fa2258bb2c7644695df；13个BF16参数/22ranges也有pins。但实际各阶段reference/actual内容hash及观察到的runtime/ELF身份藏在未保留的私有manifest/snapshot中，只有不透明文件SHA不足以验证将来重建字节等于本次数据。
  因此当前结果是完整M128模型限定门禁通过，不标记same-stimulus RTL replay ready。下一补丁仅输出路径无关logical-ID/shape/dtype/layout/bytecount/contentSHA及必要runtime/source pins的安全身份清单，绑定终态回执；不上传数组/权重，不改数值/门限/预算。完成新的内容身份固化验收后再作同刺激RTL回放。其余四block尚无同级M128结果，1024/1224未启动。


- **done：QK-only策略默认关闭的原Host/kernel选择透传。** [可移植候选](../candidates/qwen2_resident_matrix/attention_qk16_host_selection/README.md)从正确的83源QK16已组合closure出发，保持原kernel全部packed client/mux/stepsDrained/result/done/abort与债务接线，沿原HostBlockCollection→HostBlockTop→QwenOwnerKernel→Qwen2ContinuousBlock追加默认false参数，不替换顶层/命令ABI/物理端口，不改变既有emitters。初稿错误采用raw kernel已在编译前被审查拦截并废弃。
  新BF16形状限制仅作用于新BF16 opt-in；旧packed=true/BF16=false的既有非8960 FFN形状不收紧。原Qwen3.5 M1 profile限制保留。实际源变化仅2个owner/top文件＋字节不变的既有BF16 core片段，不新增Reg/Mem/IO/Module或改变Matrix几何。
  root/独立11+11源码回归通过；单次复制closure的Scala类编译83源/474类，exit0，29.4739秒，87 jars/Java/源postflight核验及有界严格清理proof通过。独立零退出/非零/TERM和deadline负例覆盖编译管理。没有elaboration/RTL/协议或完整block硬件通过。
  目前只具备从原顶层构造选择QK片段的能力；完整official policy、scratch acquire/ACK/release、六head/panel/PV及真实Host完成围栏仍未执行验证。M128模型指定27门禁与此硬件候选为不同证据层，不能互相替代。

## 下一步，保持默认关闭并逐项验收

1. **done：收齐be00失败结果。** 安全摘要/source身份已归档，数值比较和postflight未完成。新候选独立冻结，不据小切片推定旧运行PASS。
2. **ongoing：原owner可选packed接入。** 在原OfficialAttentionOwner及原Matrix服务上增加
   明确profile2路径，接真实DDR/共享银行与原输入，保留原算术、默认路径和完整golden；
   M1/M2的selected-fault围栏、返回/ACK/abort债务已验证；完整M16的27个assigned官方门限已通过，见下方原始证据；全29节点仍未闭合。真实16-key分块的有界M17/M32校验已通过；实际M17捕获、原M128资产准入及完整21事件接入的冷资格已通过。完整M128于23:57:36 UTC启动，在31.690888秒因遗留raw-KV M16行数门禁失败退出，尚未算术/比较；原界限未触发。独立run_gate已修复并通过实际准入探针；新尝试的会话连续性待确认，详见新增记录。不能以循环M1替代。
3. **ongoing：A复用最小切片。** 按[源审计](../candidates/qwen2_resident_matrix/dense_a_reuse_audit/README_CN.md)
   保持同K的context-inner顺序；A gather从1,462,272降为298,496只是源级预期。
   Queue4→3加256 B hold已接实际Chisel并通过前端资源核验，活跃payload1280→1216 B。有界解释执行在240秒超时，未取得握手通过证据，详见[失败归档](U00_2_A_HOLD_INTERPRETER_FAILURE_20261016_CN.md)；不扩大预算盲目重跑。cache不等于FFN重叠或新增SRAM端口。
4. **to do：W供数替代方案。** 先保留实际maxBeats16/1KiB配置，比较同K相邻context的
   row coalescing与另行冻结格式的tiled W；更大mailbox/多在途均须独立资源和协议账。
   原逐64B sole-active路径至少2,924,544服务边沿，A复用不会减少93,585,408 B的W。
   不将AXI内部在途数当owner并发，也不填理想DDR延迟冒充实测。
5. **to do：合并真实资源调度，再进入RTL。** panel384 B、A hold、SFU配置及三tile生命周期
   各自入账，明确bank读写冲突和返回保留。保持原数值门限，完成真实RTL全block数值后，
   再按固定wall起止测80%阶段指标与90%最终指标；任何孤立上界或软件加速均不能替代。

本文件仅整理已有回执/源码和当前运行状态，没有启动新的数值、native或RTL任务。
发布保留复现脚本、pins、hash与摘要，不附权重、输入/输出tensor或完整phase数组。

## 2026-10-17 08:26 UTC：同刺激身份补齐与原kernel接线

- **done：同刺激身份输出源码与冷验证；ongoing：实际冻结验证。** 新增标准库元数据输出器，绑定两档M16/M128的输入、参数、两类独立参考、实际19输出/SiLU/10字段观测及编译环境身份；明确13个loaded provider仅为终态认证metadata。仅输出逻辑名称、形状、编码、政策和hash，不上传张量/权重。
- 原423静态数值源码、算术、终态门禁、绝对预算保持不变；六个raw文件变化包含parent/emitter/tests/input contract/精确新增第八个artifact路径。root独立707+707冷测试通过，424文件组合、465原始源码前后不变。冷测未执行生产数值、native编译或RTL。
- 后继实际运行须在完整Git内容闭包校验后启动一次同host新M16→M128验证。原2e591b6指定27门禁PASS保留，历史逐阶段内容hash不能从旧摘要恢复。新元数据失败会保留实际数值回执，并令freeze readiness失败；不放宽deadline。
- **done：原完整Host路径九文件固定main源码审计；ongoing：生产kernel QKV reduction窄接线。** official BF16政策尚未将QKV split-K/reverse-pair coordinator接入生产kernel。第一片默认关闭，复用原Dense银行、Matrix、SFU16、iDMA；补binaryAdd透传，resident显式false，事务归属不复用会锁死window准入的ordinary active。
- 原Attention可作为功能数值基线候选，但固定4096 MAC/fullblock分母理想上界约48.187%，不满足80/90目标。packed Attention与SFU/调度优化仍必需；上述上界不是周期预测或RTL实测。当前完整RTL仍0/5。

## 2026-10-17 08:44 UTC：生产QKV reduction候选类编译完成

- **done：默认关闭生产kernel接线v2的源码冷资格及Scala class编译。** [便携候选](../candidates/qwen2_resident_matrix/production_qkv_reduction/README_CN.md)保留原Host、单Dense/Matrix4096/SFU16/iDMA。root/作者/独立13+13冷测及77文件重放通过；独立108组边沿、120种债务退休顺序仅为源码控制模型。
- v1 held success遇晚abort同时屏蔽valid/ready会锁死Host waitDone，已保留失败身份。v2保持terminal payload与握手，由原Host同拍resetRequired转Protocol；故障sticky禁止再次准入。尚未实际硬件协议签收。
- 单次真实91 Scala源码（71候选+20 HardFloat）、87固定jar，545 classes，exit0，总34.469秒；88秒绝对预算内strict scoped cleanup及源码/依赖/JDK前后核验通过。仅class compile，未elaboration/生成RTL/数值。
- 声明级新增1987bits：512bits=64B bridge lhs保持，另1475bits控制/metadata。无新SRAM或算术单元；面积/频率未实测。旧34项控制测试normal通过，旧-O18 errors为assert副作用依赖，明确未通过、不改历史源。
- 下一门：真实HostBlockCommands+router/coordinator的无SRAM/FPU小控制harness，外部服务脚本响应只验证控制，生产kernel真实债务全网仍须另验。当前仅准备，尚未运行。
- 同刺激身份冻结8ba333c run39017864296仍待终态；没有因本候选再触发数值作业。完整模型指定27门仍1/5，完整RTL0/5、90%未通过。
