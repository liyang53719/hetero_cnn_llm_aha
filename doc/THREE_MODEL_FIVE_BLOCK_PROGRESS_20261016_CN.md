# 三模型五类block：本轮计划与检查表

更新：2026-10-17 10:24 UTC。只新增状态快照，不覆盖冻结计划、源码或历史回执。
最终目标仍为同一固定配置/输入的完整实际RTL数值与状态PASS，以及
useful MAC / (4096 MAC每拍 × 完整block wall cycles) ≥90%；固定资源不能
按活跃lane缩小，DMA、stall、阶段间隙及最终写ACK均计入wall。
batch1/M128继续推进；1024/1224长序列待用户选择，不阻塞M128。

## 五类block状态

状态指完整业务接入/验收，历史组件或软件smoke不自动升级为当前完整block通过。

|目标|状态|当前真实边界与下一门|
|---|---|---|
|Qwen2-1.5B典型block，当前L0|ongoing；M128模型指定门禁done|2e591b6同host完整M128的27项assigned官方门禁与固定算术通过，21 completion/17 owner作业；8ba333c已进一步通过同刺激身份冻结；全29节点、完整Chisel/RTL与90%仍待完成。旧超时/失联历史保留。|
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

## 2026-10-17 09:32 UTC：M128实际同刺激身份冻结通过及控制解释器失败归档

- **done：新同host M16→M128实际数值与身份记录。** 8ba333c/run39017864296/job117353555753于09:09:38UTC成功；M16阶段477.007743秒，M1281499.562064秒，总2102.773260秒。仍为指定27官方门禁、28观察/10捕获、21completion/17owner作业；全29/hardware/RTL明确false。
- 实际8JSON artifact12095858179原ZIP SHA256 0c25aa1453f5b9f099fdc470933e3074462bd2f92ca08c191a1cfb9adf22b21a。replay_identity.json SHA256 84c4f626331bb68ec6fda0ae53485714c516f6a590a9b6e48a3fcfd41ea5e7fb，稳定identity 7fa82000bb935e651f517f77f50c3c37b9be457a81749129500b6e93e71b6562。root与独立checker复核通过；13个loaded providers明确仅终态认证metadata，其他持久参考/实际字节由运行内直接hash。因果观测范围、未观察sentinel和softmax FP32无额外官方tol界限保留。
- 旧离线checker把raw matrix_numeric.cpp哈希作为实际generated编译源码预期，单字段拒绝SCHEMA_VALUE；严格追溯冻结tiny.generated及两份composed图得到正确0e298008编译源图，修复checker并增加raw-map拒绝回归。原ZIP、数值源码、参考和运行未改，无重跑；corrected checker author102+102/independent122+122冷验证，实际原ZIP normal/-O通过。
- **done：控制harness源码/编译/CHIRRTL结构；未通过协议。** v7/v8/v9真实94源编译与7模块结构通过，CHIRRTL2,047,981B、0memory/extmodule/FPU。v7统一2MiB文件限额截断正常lowered FIRRTL，未callback；v8仅修生成物8MiB/log2MiB后进入callback但原60秒预算超时；v9只增marker，确认初始化/首expect/首clock均完成、最后报告cycle64，仍无scenario PASS。三版失败及strictcleanup如实归档，不将最后marker当总执行拍数。
- 停止全Host Treadle盲重试。下一门拟相同控制harness/fixture/断言的Verilator编译后端，将生成控制SystemVerilog；不是完整block RTL。固定官方工具/单CPU/native-j1/每native AS2GiB与250秒阶段预算已完成源码审查并于09:33UTC启动一次有界验证；本次停在Scala compile60秒超时，日志为空/class0、strict cleanup完成，尚未进入结构/RTL生成。原因待诊断，不扩预算重跑。Java heap1GiB不是整树硬限。完整90%目标及原Attention/SFU架构上界限制不变。

## 2026-10-17 09:51 UTC：持久身份核验工具与纯源码控制失败记录

- **done：实际同刺激身份10文件持久归档。** ca5ca9a已远端核对476文件闭包并通过载荷保护CI。原8JSON按字节保留，不含张量/权重；旧GitHub ZIP容器只保留hash及来源，不宣称到期后能恢复相同ZIP字节。
- **done：便携离线checker。** tools/offline_replay_verifier从固定8ba input-contract及checkout重建465-source view；原ZIP入口保持原digest，独立archive-body入口固定ca5ca9a/tree/member hashes并核相同identity/receipt，明确ZIP recovery=false。root/作者/独立156+156冷测通过，两条实际路线也通过；无生产数值再跑或改门限。
- **done：v7/v8/v9失败控制门纯源码复现。** 28个UTF8文件保存固定源/失败安全摘要/真实metadata generator；不提交6个可再生command/descriptor二进制表，也不文本编码替代。generator按源码生成后核原10文件hash；三版重放和6+6冷测通过。不是协议PASS。
- 后继v11固定CPU编译60秒超时，0class/0RTL；严格复用已核545生产classes的v12增量编译3测试源通过14.655秒，随后wrapper stdout marker污染Verilator版本查询，未callback。v13改独立sidecar后真实生成1,560,217B控制SystemVerilog和C++，但PCH文件触发8MiB上限，未callback。均失败并清理；不是完整block RTL数值通过。
- 下一候选使用固定Verilator已有VM_PARALLEL_BUILDS=0单TU无PCH构建选项，预算/内存/单CPU/-j1不增；待审后一次有界验证，不手改DUT或生成RTL。完整五blockM128指定27门仍1/5、完整RTL0/5、90%未通过。

## 2026-10-17 10:02 UTC：实际编译控制RTL门通过

- **done：原Host parser+QKV router/coordinator控制RTL脚本服务门。** v15实际PASS_CONTROL_ONLY，原源/fixture/断言不变，官方VM_PARALLEL_BUILDS=0无PCH单TU构建。总47.577秒；增量编译14.502、结构4.503、compiled backend27.565，各exit0且strict scoped cleanup完成。
- 94-source view完整，复用固定原545生产classes（91源），只编3测试源，新10/最终555，原545逐hash不变。原87jar→106jar转换明确81共同/6移除/25新增；没有把依赖全称相同。
- 实际生成控制SystemVerilog1,560,217B，与v13失败尝试的SV字节hash相同；本次0.gch。原Host+router+coordinator/bridge等7模块、无memory/extmodule/FPU。实际1normal+7fault通过，正常M16控制脚本18,457cycles、21completion/17jobs（13ordinary/1resident/3reduction），不含真实Dense/Matrix/SFU/iDMA算术或生产kernel五物理债务。
- 晚held reset/abort、abort_pending、window_tag、drain_short、idle ordinary/resident stray均通过；受控服务接受/回包账本排空。实际argv固定单CPU/Verilator threads1/make-j1、native每进程AS2GiB，Javaheap1GiB，不宣称整树内存硬限或硬件周期利用率。
- [纯源码复现与安全证据](../candidates/qwen2_resident_matrix/production_qkv_reduction/compiled_control/README_CN.md)提供固定工具/HardFloat/JDK依赖、生产classes重建与metadata fixture生成，包不携带classes/jars/RTL/原日志/宿主身份/权重。root/作者/独立8+8冷测与真实metadata再生通过，独立实际回执和全部源/产物身份复核通过。
- 后继原Host official/resident/QKV完整CHIRRTL结构门正在准备，固定4096资源与burstWrites/capacity1024，尚未运行。真实生产五债务、packedQK/PV/scratch/panel接入和SFU吞吐仍未闭合；不会在48.2%理想上界的串行Attention路径直接启动长M128 RTL数值。模型指定27门仍1/5，完整RTL数值0/5，80/90目标未验收。

## 2026-10-17 10:18 UTC：固定资源源码预算检查器

- **done：必要预算计数代码与独立审核。** [预算检查器](../candidates/qwen2_resident_matrix/prefill_budget_source_audit/README_PORTABLE.md)用整数/Fraction，区分raw Scalar、仅QK16未packedPV、packedQK/PV模型三配置；root/作者/独立16+16冷测、18源pins通过。source-only原链重建包含M16中间片，最终schedule SHA a65dca9d24862c2b552117ce2c9cfdb270215b12881490fc50b5545b938b6086，未执行浮点数值/RTL/EDA。
- 固定useful6,014,828,544及4096MAC/cycle，80%整块wall门为<=1,835,580 cycles，90%为<=1,631,626。保持原单Scalar服务映射，三配置Scalar接受到最后ACK必要下界依次8,391,167、8,391,167、6,310,655，单项已排除80/90，不依赖Matrix相加。只对保留原串行phase/no-overlap映射才可加成11,438,591、10,701,311、7,844,735；不得外推未来borrower或跨token流水。
- 服务间隔源码边沿Add/Mul/cutoffExp3、fullExp20、正常Div28/29；有限成功softmax每row至少一次exp(0)，全fullExp仅条件输出。最后ACK相对下次接受差一拍已保守扣除。此前81.9455%是divider单项理想上界，不代表完整调度可达。
- 最小性能路线需要现有16lane Add/Mul与SFU16的有序borrower、合法有限context/SiLU微序列、真实bank与阶段流水；现6row scratch不能免费按16row满供数。下一片仅metadata资源事件约束设计，所有未知物理映射/时序输出unresolved，不生成周期预测或80/90验收。
- 原Host完整结构v3/v4在32MiB上限失败并清理，v4测得CHIRRTL39,580,497B、672module+17extmodule定义、topHostBlockTop；未写IR，未得唯一资源/五债务结构PASS。依据实测的48MiB/768定义后继保持原90s/heap1GiB/单CPU，正在审核，未降低资源或启动长完整RTL数值。

## 2026-10-17 10:24 UTC：原Host完整CHIRRTL结构门通过

- **done：原HostBlockTop official/resident/QKV/burstWrites配置结构。** 依据v4实测仅将IR上限32→48MiB、定义门512→768，原90秒/heap1GiB/单CPU/资源及debt语义检查保持；v5真实18.499秒通过，compile4.674/emit12.754均exit0且strict scoped cleanup完成。
- CHIRRTL39,580,497B，SHA e52a110c7c7ca7446b4dad3793a7ce3f6019ebd2ecf221fe0e6220ebd246ad80，689定义/连接实例、17外部模块、68存储声明。独立递归统计及五debt的10个ready AND valid更新guard、Drained负极性依赖再次核对通过。92完整源、原545类不变+3emitter=548逐hash绑定。
- 唯一原Dense/bank、Matrix服务及8个16×32端点、SFU bank16scalar与iDMA结构存在；全top共17scalar包含原单Scalar。4096是接口/参数配置依据，不是综合物理资源签收。capacity1024的scores/probs共8192B未偷减为M128容量。
- [安全源码复现包](../candidates/qwen2_resident_matrix/production_qkv_reduction/host_structure/README_CN.md)仅源码/pin/实际结果安全投影，原39.6MB IR、classes/jars及宿主回执不提交；root与独立6+6结构冷测、4+4便携冷测通过。v3/v4失败原样保留。
- 本次无新SystemVerilog、无作业/动态协议/数值/利用率执行；5条既有索引width警告保留。17ext仅三类defname（8seed-enabled matrix endpoint、8tc_clk_gating、1iDMA wrapper），provider完整闭包正在核对。冻结6SV仅增量，不能直接混旧无seed array；官方iDMA固定依赖锁与历史报告差异需按真实导出COMMITS/SHA256SUMS解决，不能将结构PASS称外部RTL链接PASS。


## 2026-10-17 10:50 UTC：固定 iDMA 源导出候选与单池 prefill 元数据片

- **done：source-export v5 源码/冷资格；pending：真实源导出。** 本批只保留已审 11 个明确清单文件，冷测试 28+28 通过；没有运行真实 fetch、Bender、uv/make 源生成，也没有 Verilator、firtool、仿真或综合结果。新 [iDMA source-export workflow](../.github/workflows/idma-source-rebuild-20261017.yml) 仅在 main 上自身 YAML 路径变化时触发；本批发布允许一次 source-only 尝试，之后再修改该 YAML 仍会再次触发，不能宣称技术上永不重跑。其他原 workflow 与 465 个模型运行源字节不变。
- 源生成保持固定上游、lock、依赖 commit 与工具身份；Bender 的 script verilator 只输出文本 filelist，不执行 Verilator。上游 .python-version 偏好 3.11，但 pyproject 允许 >=3.11；候选按已审决定使用 CI 现有 3.12，并记录实际解释器版本/hash，显式 UV_PYTHON、禁止自动下载 Python，保留 --locked。不把该偏好差异写成已实际验证；资格失败时不自动换版本或放宽锁。
- 生成总预算 900 秒、单命令最多 180 秒，沿原绝对 stop 使用严格 owned-group 清理。工作树总量 1 GiB 是采样 soft cap，不是硬磁盘 quota，采样间可暂时超量；单文件 64 MiB 硬限及归档展开/复制前检查不能替代该说明。成功后 artifact 仅限核验的公开源树 idma_export 与 SAFE_IDENTITY，包含所需隐藏源文件；不上传工具、缓存、pycache、凭据、权重或数值数组。当前 source-export 实际结果仍 pending。
- **done：四个 source-only/metadata 小片的独立冷审查；ongoing：真实 owner 供数接线。** [联合事件账本](../candidates/qwen2_resident_matrix/prefill_joint_event_ledger/README_CN.md) 8 文件、[SFU loan 双 profile](../candidates/qwen2_resident_matrix/prefill_sfu_loan_profiles/README_CN.md) 8 文件、[单一生产 SFU16 池联合模型](../candidates/qwen2_resident_matrix/prefill_single_pool_joint/README_CN.md) 10 文件，以及 [operand/address 映射](../candidates/qwen2_resident_matrix/prefill_operand_mapping/REPORT_CN.md) 7 文件只约束身份、债务、原子边沿与整数索引。外部 ready/return/accepted 事件不是自证可执行调度；can_supply 仍 False，没有数值、RTL、完整 prefill 或 80%/90% 实测通过，也没有新增第二个 SFU 池或免费 SRAM/寄存器/端口。
- **done：width5 合法事务范围源码审计 3+3。** 该结论只覆盖所审合法事务范围，不作任意故障安全结论；本批不附该报告，保留到后续小批，不扩大本次 45 文件清单。
- 既有 Qwen2 完整 M128 模型限定指定 27 门禁及同刺激内容身份结果保留，五 block 进度仍为模型限定 M128 1/5、full RTL 0/5；全 29 节点及完整张量覆盖缺口不因本批 metadata 或 source-export 候选而关闭。


## 2026-10-17 11:18 UTC：iDMA 首次失败归档、v6 条件闭包修复与生产 QK16 类编译

- **failed：首次 source-only 导出；pending：v6 实际导出。** [原失败安全证据](../reports/execution/IDMA_SOURCE_EXPORT_FAILED_39026847303/README_CN.md)保留 commit95db862b5b79a86dca7fac98343441d53f7f7bee、run39026847303/job117379407493、attempt1 的 failure。28+28 冷测及工具 bootstrap 成功，但 SOURCE_CLOSURE 阶段拒绝 uvm_macros.svh，后验与上传跳过，artifact 数量 0；没有可复用 provider 包、最终导出身份或 cleanup 终态的独立证明。没有重跑原 run。
- 固定 common_cells 源码把该 include 放在 ifdef UVM 的 package 内，原扫描器未区分 inactive 分支。此为固定源与控制流诊断；实际 filelist、原错误的 include 来源路径及私有 stage receipt 未保留，不把源码推断冒充运行产物。前置命令返回不等于整个 source-export 闭包通过。
- **done：v6 独审 source-only GO 与 64+64 冷测；pending：新提交实际一次尝试。** 保持官方 source/tool/lock pins、原生成目标、Python 3.12 选择、900 秒总预算与严格 cleanup；工作树 1 GiB 仍为采样 soft cap，不是硬 quota。按实际 filelist 宏集合及顺序作有界条件 include 检查，递归共享 define/undef 状态；不支持的宏/条件语法保守拒绝，不宣称完整 SV 预处理器或 RTL 可编译验收。没有下载 UVM、删官方源或改依赖来绕过失败。
- 同一 [source-export YAML](../.github/workflows/idma-source-rebuild-20261017.yml) 的修复发布仅授权一次新的 source-only 运行；仍只匹配自身 YAML 路径，不修改其他原 workflow。新 always 步骤只上传固定 IDMA_SAFE_OUTCOME.json 白名单；缺失 receipt 可报告 missing，stage cleanup 标记不证明全局终态，global_cleanup_verified 恒 false。成功源树 artifact 仍仅 success() 上传；不上传原日志、private receipt/proof、工具/缓存、半成品源树、权重或数组。
- **done：production QK16 默认关闭重基及一次真实 Scala classcompile。** [可移植包](../candidates/qwen2_resident_matrix/production_qk16_rebase/classcompile/README_PORTABLE_CN.md)完整保留原 10 文件 source recipe 哈希；根 README 的“未 classcompile”是历史源码审查检查点，当前另附 92 源→550 classes、74.776 秒、exit0 的实际编译安全摘要。原执行 runner 与新显式路径便携适配身份分开：便携 driver 只作冷测/preflight，没有第二次 Java；仅 classcompile，不是 elaboration、RTL、协议、数值或供数通过。
- QK-only 路径复用原 production 完整 BF16 policy、原 Matrix/Dense/SFU/iDMA，active M≤128 的限制只针对选中 Attention 作业，原 capacity1024 不变；旧 softmax/PV 与五债务正文保持。没有新增 payload 数组声明，但复用 denseWeights 可能重新激活最多 8192 bit，另有 99 bit 控制声明及 mux/路由成本，物理 retention/area/timing 未证明；不能写成零成本或 packed PV 已供数。
- 本批交付 43 路径（v6 17＋原失败安全证据 3＋QK 22＋进度 plan 1）；9 个既有 source-export 文件字节不变，实际 commit 差分为 31 新增、3 修改。原 465 个模型运行源不变，模型限定 M128 1/5、指定 27 门禁及已固化内容身份保留；full RTL 0/5、全 29/全张量覆盖缺口、80%/90% 验收与 can_supply=False 均不因本批改变。


## 2026-10-17 11:52 UTC：原 QK16 Host 同 IR 离线结构门与 iDMA v8 源导出候选

- **failed：原 QK16 Host 生成 driver 总门；done：同一 IR 的离线结构验证。** [23 文件源包与安全投影](../candidates/qwen2_resident_matrix/production_qkv_reduction/qk16_host_structure/README_CN.md)保留原 v3 driver exit1/receipt NOT_COMPLETED。编译与 CHIRRTL 子阶段 exit0 后，旧 parser 误拒绝两条已有 memory 读地址默认 invalidate；不能把原失败改成 PASS。随后 v4 只读同一 IR，不重跑 Java，完成 93 源、原 550＋emitter3 类、SourceFile/87jar/JDK postflight 及 4407 条连接检查，独审通过；本包/root 25+25 冷测通过。
- 实际 IR 为 42,095,784 B，690 定义/实例（17 ext）、68 memory 声明，5 条既有位宽 warning。原 4096-MAC 配置、16-lane SFU、全 top 17 scalar、单 Dense/Matrix/iDMA 与五债务接线结构可核；没有动态协议、数值、性能或综合资源验收。QK-only 仍没有完整 packed PV/scratch/panel 供数；未上传 IR/classes/JAR、原日志或主机进程身份。原 90 秒生成预算与独立 120 秒上游类编译预算分别保留，不能合并或继承为新执行 PASS。
- **failed：第二次真实 source-export；done：固定官方预处理微资格 v3。** [第二次失败记录](../reports/execution/IDMA_SOURCE_EXPORT_FAILED_39028560366/RUN_OUTCOME.json)保留 commit23f9a441d85433782108b6d0ad60eb967fbf801a、run39028560366/job117384281352、attempt1 的 failure，原 run 未重跑。SOURCE_CLOSURE 报 unsupported bare backtick；成功记录了57个命令阶段，但 source artifact 数量0，独立 global cleanup 终态未证明。合法注释构造与 identifier token-paste 被手写检查器误拒是固定 header 复现诊断；原失败实际 filelist/生成文件未上传，不能扩大为完整运行产物结论。第一次 run39026847303 的失败不变。
- [微资格 v3](../reports/execution/IDMA_PREPROCESS_QUALIFICATION_V3_20261017/README_CN.md)一次实际6 case 的预期退出为0/1/0/1/0/0，另3个路径/源line负例在 preflight 拒绝；UVM 开关、缺 include、合法注释/identifier paste、已知内建宏和 -E --MMD 依赖输出通过。此前 v2 因漏一个固定 fixture 仍总 FAIL；v3 补固定 header 后独立获批一次，不改旧结果。微资格不是完整 iDMA source-export，也不是 RTL/数值通过。
- **done：v8 独审及 root 72+72 冷测；pending：完整真实 source-export 新尝试。** [source-export 脚本](../scripts/idma_source_export_20261017/export_source.py)改用固定官方 Verilator binary 的 -E 预处理与 .d 依赖核验；只预处理，不 --cc/build/仿真/综合。固定 iDMA/七依赖/Bender.lock、Bender/uv pins 保持，官方预处理器及已验证 profile 有独立固定 hash。v7 NO-GO 历史保留，v8 修正 preprocessor_requested 命名和原 deadline 移交，不冒称 admission 已执行工具。
- 信任边界明确为固定可信源码 pins、严格 filelist 参数/直接 include 路径预检、输入与工具前后 hash、事后 .d 未知依赖拒绝；不是 OS sandbox、syscall 读取审计或任意恶意宏防护。使用工具已知内建宏，不继承 v6“无隐式宏”的口径；未来 RTL 必须使用同一 profile 或重新验证。未知动态 include/不支持语法应停下逐项审查，不宽放。手写 conditional_closure.py 和 test_conditionals.py 本批显式删除，旧 Git 历史可恢复。
- 20 分钟 job、900 秒源导出＋终验、180 秒单 stage 与原 stop 内严格 absence barrier 保持；新增 -E stdout 专用32MiB采样/末检限，单文件64MiB硬限、4GiB AS、1CPU、源树1GiB采样 soft cap。soft cap 不是硬磁盘配额，不自动扩大预算或重试。成功源树仅 success() 上传，always 白名单安全摘要不替代最终 job 或全局 cleanup 证明。
- 本批只发布上述源/安全摘要与本进度更新，不等待或并入正在独立推进的 FMA 结果。同一 source-only YAML 修复发布只授权一次新尝试，原其他 workflow、465 个模型运行源字节不变。模型限定 M128 1/5、指定27门禁与已有内容身份保持；full RTL 0/5、全29/全张量覆盖、真实供数与80%/90%实测验收仍待闭合。


## 2026-10-17 12:07 UTC：固定 iDMA 源导出成功与四个既有 FMA 组件接口门

- **done：固定 iDMA source-export v8 实际成功。** [8 文件安全证据](../reports/execution/IDMA_SOURCE_EXPORT_SUCCESS_39030773068/README_CN.md)绑定 commit0077355800e3040dfdd6d79def697f3ff6456c2c、run39030773068/job117390605122、attempt1。实际源 artifact12099239717 已下载并独立逐文件核验，927 manifest 条目通过，另 manifest 自身共928文件、33,744,483字节；源 ZIP SHA a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce。此小包仅保留安全身份与复核摘要，不包含该33MB物化源树。
- 实际294个 source、8个 include目录、312个准入输入与309个记录依赖；固定 Verilator5.032 的 -E --no-std --relative-includes --MMD 单 compilation-unit profile 通过。初始宏为 TARGET_ASIC/TARGET_RTL/TARGET_SYNTHESIS/TARGET_VERILATOR，已知工具内建宏保留，UVM 不在初始集合。预处理 stdout6,288,028B、stderr0B；未来消费者改变 profile 必须重验。此门证明固定源生成、物化、预处理闭包与hash一致性，不代表 Host 编译、综合、动态协议或数值验收，也不是 OS sandbox/任意恶意宏防护。
- 58个记录 stage 均 exit0/cleanup verified，范围仅原锚定组与已观察身份；global_cleanup_verified=false。原 stdout/.d/私有 proof 未随 artifact 保留，安全摘要不能重新认证原进程身份或全局 absence。原两次 source-export 失败39026847303/39028560366和微资格v2失败均保留，微资格v3仍单独限定。原900秒总/180秒stage/32MiB stdout采样末检与1GiB树soft cap不变。
- 源 artifact 为30天保留，官方到期记录为2026-11-16；不把它当永久源归档。已发布18文件脚本、官方 source/tool pins、锁和实际内容hash用于后续经授权的独立重建；新输出/工具记录/ZIP封装或路径依赖可能不同，不重跑旧run、不自动继承PASS或静默接受内容漂移。本批不修改任何 workflow，因此不会再次触发 source-export。
- **done：既有四段 FMA 组件 SV 发射与接口核验。** [22 文件可移植 recipe/安全投影](../candidates/qwen2_resident_matrix/production_qkv_reduction/fma_components/README_CN.md)记录单次v2成功：93源，原550类逐hash复用，独立App3类，8.617秒；HeteroBF16FmaPre/Mul/Post/Round四份SystemVerilog共8个模块定义，端口与固定 seed-enabled Matrix lane 四段绑定/位宽匹配。root及独审12+12冷测通过；原计划/未执行v1历史与实际v2结果分开，安全投影不是原receipt字节。
- 该门仅四组件SV与interface-only；没有算术测试、完整Host链接、动态债务、性能或完整block RTL通过。此包没有生成SV/IR/classes/JAR/原日志/宿主身份，保留重建脚本与pins；独立上游120秒类编译和本组件90秒总预算不可混同。本批没有再运行Java/firtool或短Kernelbench，短Kernelbench仍未执行。
- 本批30个add-only源/安全证据文件＋本plan更新；原465模型运行源和整个.github字节保持不变。模型限定M128 1/5、指定27门禁及已有内容身份保留，full RTL 0/5，全29/全张量覆盖、端到端真实供数和80%/90%实测目标仍未完成。


## 2026-10-17 12:48 UTC：原生产 SFU 反馈最小源码修复检查点

- **done：19 文件可移植源码/安全证据检查点。** [SFU feedback 修复](../candidates/qwen2_resident_matrix/production_qk16_rebase/silu_feedback_fix/README_CN.md)保留原生产 FfnTileSiluBridge，仅将 SFU abort 从 bad 改为外部 io.abort || 现有 poison；tiles.abort 仍立即使用 bad。当拍 bad 仍阻写/新请求，错误结果当拍消费并登记 poison，外部 abort 不延迟。新增寄存器、存储与算术资源均为0；固定原 top 和资源配置未改变。
- **原失败完整保留。** 原 B1 实际 firtool 在51.650秒发现 resident/router/真实 VectorSilu loan 组合环并 exit1，没有完成SV。修复后的单源增量编译器 exit0，但严格 ABI 完全相等后验因新增 public reflection helper72 而 FAIL，该次实际运行仍为 NOT_COMPLETED。随后独立精确离线字节码兼容复核 PASS，不重跑Java，不把离线兼容改写成原严格门通过。
- 离线证据约束原实际557类及修复后557类；553类逐hash不变，4类归属同源。72个反射目标序列、Code hash及实际调用点固定，所有非Bridge类没有相应外部helper引用。新增helper不是任意忽略项；结构ABI边界不含所有annotation或方法体等价。root与独审17+17冷测通过，包括12握手/错误路径及5可移植重建/兼容边界；这些冷测不证明完整电路动态行为。
- 公共重建链从已发布 classcompile/README_PORTABLE_CN.md 的生产/QK donor/HardFloat20源恢复原92源，再应用固定单表达式修复；可选两个已pin bench源码形成94源。原 compile_only.py 会拒绝修改后的源pins，不能绕过；新A/后续B1需要各自经审runner、精确闭包和预算。新A已获授权并正在独立执行，但本批不收录或声称其结果；没有新 CHIRRTL/SV 无环、完整Host、数值或性能通过声明。
- SAFE_RESULT仅白名单投影，保留原receipt hash、阶段统计及cleanup相对时差，不是原receipt字节；本包不含classes、IR、生成SV、JAR、权重、原日志或机器PID/boot/group身份。没有历史class字节时可重建源/跑冷模型，但不能宣称重放历史字节码证据。
- 本批19个add-only文件加本plan追加，原465模型运行源与整个.github字节不变，不重复触发iDMA source-export。模型限定M128 1/5、指定27门禁及内容身份不变，full RTL 0/5；全29/全张量、端到端真实供数、短Kernelbench和性能目标仍未完成。此源码检查点不继承正在运行的任何新结果。


## 2026-10-17 13:22 UTC：修复后真实 Kernel SV 与同输出离线库存门

- **done：修复后真实 Kernel 完整 SV 生成。** [26 文件源码/安全历史包](../candidates/qwen2_resident_matrix/production_qk16_rebase/silu_feedback_sv_qualification/README_CN.md)记录固定 firtool 对修复后原生产 Kernel 的实际生成：exit0、96.221966秒，69,464,271B SV，SHA256 93fe8475e21fe1efefc99efac1ab13bf670a48a3cd239351c4efa5b14e815451。真实组合环检查已完成通过；该进展替代此前“尚未验证修复后无环”的待办，但不抹去原 B1 的组合环 FAIL。
- **原运行和后续复核分开。** 128MiB 写出上限的原 v7 整体仍为 NOT_COMPLETED：工具完整生成 SV 后，原库存 checker 将同名类型/实例名称误算两次而拒绝。独立修复仅跳过已完整解析的 instance span；同一实际 SV 的只读离线复核 PASS，root/独审8+8冷测通过。没有重跑工具或将原 receipt 改写为 PASS。
- 后验覆盖49个定义、目标原 Bench 子树的8个 endpoint、8个 clock gate、1个 iDMA的受限直接实例库存与 named-port；完整 provider link/B2、动态协议和数值尚未通过。完整 full block RTL、利用率与端到端供数也没有因此取得通过资格。
- 原历史保留：原组合环exit1；两次60秒 timeout，其中诊断确认环检查 Done 于43.284秒；48MiB文件写出失败；128MiB完整写出后库存误拒；以及独立同SV离线 PASS。安全投影保留 receipt/log/output hash、相对cleanup与明确标为 direct-leader sample 的统计，不是原receipt/proof字节，不声称进程树峰值或重新认证机器身份。
- 仍有两个共同命名空间阻点：RoundRawFNToRecFN_e8_s24 与 RoundAnyRawFNToRecFN_ie8_is26_oe8_os24 在独立FMA provider与本SV中同名但接口/内容不同，不能任选覆盖或手改生成SV。当前方案是在同一 Chisel 命名空间共同发射原 Bench 与四FMA；collection仅发射容器，目标top仍原 Bench。新共同发射A正在另行授权执行，本批不纳入其结果；后续动态必须消费同一合格资产，不能用独立再发射替代闭包。
- 公共链保留原92源重建、相邻单表达式修复/bench94源、本包独立emitter形成95源；generation_v7/PLAN_CN.md的“尚未执行”标题仅为当时冻结的历史计划，当前实际生成结果以SAFE_HISTORY为准；历史 generation_v7 原checker及输入/工具/IR/receipt pins保持，完整重建产生新receipt须另建受审闭包，不修改冻结身份。没有历史同hash SV时只能运行冷测，不能宣称离线复核了该69MB实际输出。
- 本批仅26个add-only UTF-8源码/安全元数据和本plan追加，不上传69MB SV、39MB IR、classes、JAR、权重、机器PID/boot/session/group或原日志。原465模型运行源与整个.github字节保持不变，不重复触发 source-export/昂贵运行。模型限定 M128 1/5、指定27门禁及已保留内容身份不变，full RTL 0/5；全29/全张量覆盖、真实供数和性能目标仍待完成。


## 2026-10-17 14:00 UTC：共同命名空间与两个原 provider 分层 lint 门

- **done：共同命名空间 A/B1 实际通过。** [50 文件共同发射/endpoint检查点](../candidates/qwen2_resident_matrix/production_qk16_rebase/collection_provider_qualification/README_CN.md)保留原95源、557类复用＋4个新emitter类；共同 CHIRRTL 39,466,374B，共同 SV 69,711,072B，SHA256 53f4f4cb503fc9fd9e7bf72d8e52a6ffc842d70959f847098ea817df11ba933f。56唯一定义、原Bench76端口、四FMA端口及Bench内8endpoint/8clock/1iDMA库存通过；同名不同义的两helper不再由分别生成文件任意覆盖。collection仅生成容器，资格top仍原Bench或明确的分层endpoint，不替换原目标。
- **完整4096 Bench仍未通过。** 真实provider整链lint在AS4GiB下std::bad_alloc，481个warning保留，原FAIL不改写；stage元数据128MiB文件上限误写与实际native16MiB差别亦保留。新的AS6GiB/full4096门目前只准备，不在本批报告执行或结果；分层门不能冒充整链、动态、数值或full block RTL资格。
- **done：原512 endpoint分层lint。** 原32cluster×16lane=512、seed1及共同FMA在14文件闭包下真实lint exit0、零warning，stage41.671秒/总42.026秒；原v1无尺寸-G参数产生唯一WIDTHTRUNC的FAIL保留，v2只把参数token明确为1'b1，未屏蔽warning。工具内部116个C++文件统计不代表实际写出或build，目录未生成相应构建物。
- **done：原iDMA flat wrapper固定参数lint。** [24 文件安全证据/原runner](../reports/execution/IDMA_WRAPPER_LINT_V3_20261017/README_CN.md)记录原top idma_backend_rw_axi_flat_wrap的v3 PASS，固定512-bit数据/64-bit地址、BufferDepth3、HardwareLegalizer1、RejectZeroTransfers1、EnableCompute0；293顺序输入及1039 source/tool pins前后核验通过，source/ABI不改。stage1.210810088秒、总1.553870136秒，实际零warning、exit0，没有C++build/仿真/数值。
- 原23 WIDTH诊断在固定参数与有效非零事务范围内审计，落实21个精确file/rule/line/hash waiver；无效周期不继承该值域结论，其余warning仍fatal，未豁免PINMISSING或UNOPTFLAT。6个官方结构提示隔离FIFO valid/ready、write first/last、coupler aw_sent及内部write_req_o；top public split已移除。工具无独立hint-hit telemetry，结论限该完整固定lint，不能推广任意top/宏/参数或动态功能。v1的4个UNOPTFLAT失败、v2的public SPLITVAR误用及剩余2个UNOPTFLAT失败完整保留。
- root按公共README复核collection的19+19/8+8及wrapper恢复布局后的15+15冷测通过。structure原冷fixture依赖历史大IR，只保留原测试源码及边界，不冒称无IR环境重放全部结构测试。原阶段PLAN是冻结历史，当前实际结果以SAFE_HISTORY/ATTEMPT安全投影为准；这些投影不是原receipt或完整机器cleanup proof，也不声称全局absence或全进程树真实峰值。
- 公共重建链和精确源/工具/依赖/生成物hash保持，历史大IR/SV不存在时不能假称复核其原字节；新输出或receipt必须另行受审绑定。本批不带69MB SV/39MB IR、33MB iDMA物化源树、class/JAR/工具二进制、原日志或机器身份proof；不执行打包内runner。新增50个collection文件＋24个wrapper文件＋本plan追加，原465模型运行源和整个.github保持不变，不重复触发source-export或昂贵运行。
- 模型限定M128 1/5、指定27门禁和内容身份不变，full RTL 0/5。完整原Bench/Host链接、动态供数、RTL数值、全29/全张量覆盖与性能目标仍待后续闭合；此批不继承正在准备的新门结果。


## 2026-10-17 14:35 UTC：seed/DMA 最小修复与完整 profile 失败检查点

- **done：原 BEGIN provider 组件 lint 通过。** [57 文件源码/安全历史包](../candidates/qwen2_resident_matrix/production_qk16_rebase/seed_dma_provider_checkpoint/README_CN.md)固定原 front-control baseline、按序 BEGIN 与 reserved-ready 两个最小补丁、DMA两项结构提示及历史runner。BEGIN将ready拆出可独立准入条件，已接受流水仍保留fullquiet fault；原512-lane组件真实工具门PASS，总41.499秒。此组件结果只覆盖BEGIN版本，不传递为后续reserved修复或4096整体通过。
- **done仅限源码/布尔模型：reserved-ready修复。** 两个ready使用同一retainedquiet，65536个二态边界组合输出/ready/fire等价，非法提前beat/commit仍拒绝，busy持valid仍原poison；不新增状态位、端口或算术bank、不缩4096。该证据不证明完整动态FSM、X/Z或RTL数值；没有冒用BEGIN版本的组件PASS。DMA在原6个官方提示后仅新增内部read_req_o/read_rsp_i两精确split，provider原字节不改，不靠关闭UNOPTFLAT。
- **完整原4096资格仍全部FAIL。** 原AS4GiB bad_alloc与481warning保留；修过iDMA的AS6GiB完整门仍bad_alloc并报seed BEGIN结构SCC；BEGIN后的noinline完整门180秒工具预算耗尽，并暴露beat/commit与DMA两SCC；合并reserved-ready、DMA split、noinline/nodfg的最新完整门约54.17秒工具阶段再次AS6GiB bad_alloc（总56.317秒）。最后日志零warning不表示相关检查已完成，不能升级为PASS。所有原receipt状态、log hash及失败历史保持。
- 源码与工具优化profile分开：noinline/nodfg改变工具优化路径，未跳过设计子树/黑盒化/缩阵列；合并多项变化不能归因单项性能改善。原CPU1、AS6GiB、210总/180工具、10cleanup、16MiB文件、2MiB日志、64MiB树软限和21精准WIDTH规则保留。旧AS4G receipt误写128MiB与实际native16MiB的差别按实际native_limits披露，不修改旧证据。
- **停止monolithic盲调。** 不再自动重跑或盲目增加AS/时限、放宽warning。下一步仅准备官方 hierarchical 真实库生成的最小微资格，尚未执行；必须观察真实子库生成/构建和链接边界，不能以--lint-only冒充已分层、不能以原单组件或工具配置代替实际库结果。后续执行需要独立受审候选与一次明确授权，本批不承诺或报告新结果。
- root与独审按verify_package正常/-O复核通过：只核冻结hash、两套纯Python边界枚举及单source按序delta，不启动Java/EDA/子进程。原历史test_cold部分需要完整固定布局，保留范围，不冒称任意目录已重放全部历史工具门。full_profile的“待独审及授权”是原候选历史README；当前实际失败以主README与SAFE_HISTORY为准。
- 本包含三个小型手写baseline/修复provider源码快照及patch，不包含大生成SV/IR、classes/JAR、完整上游源树、工具二进制、原日志或私有机器proof。公共重建链、源/工具/input pins和历史输出hash保留；重建生成新receipt需重新资格，安全投影不是原receipt/cleanup proof，也不声称全局absence或进程树峰值。57个add-only交付文件＋本plan追加，原465模型运行源和整个.github字节不变，不重复触发source-export或昂贵运行。
- 模型限定M128 1/5、指定27门禁和内容身份不变，full RTL 0/5。完整4096/Host链接、动态供数、RTL数值、全29/全张量及性能目标仍未完成。


## 2026-10-17 20:01 UTC：独立小批源码检查点

本次仅新增 development_snapshots/canonical_host_source_only_20261017/ 的独立源码快照：手写 AXI 收支账本、Python 完成保持合同、最小冷测试及中文边界。两份项目源码逐字保留，正常与 -O 的隔离冷测各 14 项通过；不包含系统工具链、头文件或库的环境清单，不改变此前较大证据包的未发布状态。

- done：上述小批源码与合成合同冷验证。C++ 未编译，不能据此声称该片段真实硬件绑定或完整驱动通过。
- done（另有本地实际证据，未由本小包重新验证）：原 Kernel 合成 M1、一次 M17 跨 tile 任务完成实际 RTL 数值比较及 AXI/完成保持检查。此为 Attention 短链，不能替代完整 Host/block/M128。
- ongoing：复用原 HostBlockTop、官方冻结 M128 输入与参考，继续 canonical 装载、真实观察器、27 节点观察和 Host 回放接线。原 Host QKV/resident/metadata/prefix 接线已存在；当前新增适配仍按源码、class、RTL、实际运行分层验收。
- todo：Qwen2 完整 M128 同刺激 Host RTL 数值验收，然后按既定顺序推进另外四个 block；完整 block RTL 仍 0/5。1024/1224 未开始。
- todo：固定 4096 MAC 和完整 block launch 至最终 ACK 周期分母的实际利用率验收，80% 下限及 90% 目标保持；当前没有完整 block RTL 利用率达标结论。

本小快照的发布不包含权重、npz、canonical raw/reference 数组、生成模型或二进制。Git 远端和相关 CI 需按最终提交 SHA 单独核验，源码冷测不代表 CI 或 RTL 通过。


## 2026-10-17 21:18 UTC：三源只读观察源码检查点

- done：新增 development_snapshots/canonical_host_observation_taps_source_20261017/ 独立项目源码快照，包含三份候选 Scala、三份原 baseline、原补丁、自包含反投影冷测与中文证据边界。三源正向重放与删除观察插入后的反投影均逐字一致，正常/-O 各12项冷测通过。
- done（独立实际 class 层证据）：同一组三源在完整95源 fresh编译中通过，实际569类、9个观察Bundle；该次编译约69.98秒。当前小快照不构成完整编译工程，也不携带编译器或环境清单。
- 资源口径：仅新增9束、2604位命名组合观察，源码无新增寄存器/队列/算术/MAC/Host外部端口；这不是物理网表面积或时序证明。固定4096 MAC及完整block周期分母保持，不以观察线或局部活跃lane改变分母。
- ongoing：新tap闭包的Host IR/SV检查、实际层次绑定、B退休与resident/loan身份关联、27节点完整覆盖。prob须取真实PV请求归一化BF16值，不能以exp SRAM冒充；SiLU raw valid须联合resident及loan/abort/poison资格。尚无新tap运行通过结论。
- done（另有本地实际记录，非此小包复跑）：完整14 provider和2份metadata经C++加载并封存RAM，16区域回读SHA相等；这是loader/RAM资格，不是Host执行。
- todo：同一官方M128冻结输入/参考下的完整Host/block RTL数值验收，及固定资源完整周期利用率实测；完整block RTL保持0/5，90%目标不降低。

只提交项目源码/项目源SHA和说明，不含权重、原始输入参考、生成模型、class/JAR/JDK、系统工具链/头文件/库环境清单或原始进程日志。此前环境清单公开许可问题保持独立待确认。新提交远端与CI仍按其SHA独立核验，不继承旧提交检查。


## 2026-10-17 23:01 UTC：SiLU 观察器纯源码保存与实际 Host RTL 进度

- done：保存六文件源码小片 development_snapshots/canonical_host_silu_observer_source_20261017；两项原源码逐字保留，其余为明确标记的便携测试、逻辑信号投影与中文说明。独立目录 normal/-O 各 28 项通过；仅 Python 合同/源码检查，没有编译 C++ 或执行 RTL。
- done：95 源新编译 569 class 后，真实 tapped Host CHIRRTL 已生成。原结构检查 FAIL 保留；同 IR 窄 offline 复核通过，差异仅两 mport 自动名与一 assertion 源位置，未重发 IR。
- done：firtool 生成 76,366,612 B Host 共同命名空间 SV；59 模块、83 Host 叶/833 payload、9 逻辑 tap 2604 bit 有限库存独核通过。外层错误执行说明文字导致 exit127，独立 Python exit 未记录；firtool exit0 和持久产物检查分开保留，不能追认整个 wrapper 成功。
- done：实际 SV SiLU 来源索引 468 pre/13 post，467 pre 直名与1现存 wire 别名；尚无生成 C++ 绑定。六文件仅发布逻辑 module.signal/width 派生投影，不上传原 SV、宿主路径或工具链库存。
- ongoing：首次 Host hierarchy 规划因不可达 cut 缺 clr_i 和真实 DMA BurstLen 字面量宽度警告失败；独立源码审证明精确双删与 4'd8→32'd8 同值替换。后继实际捕获已在首 MAKE 前按预期77停止，外层exit0；实际独审进行中，未 make/child codegen/link/sim。
- todo：生成真实 Host/endpoint C++、实现 GeneratedBinding 与 PhysicalObserver、27节点实际捕获和固定 M128 全 block 回放。四入口仍 Incomplete；source 索引、库存或规划不得替代运行数值证据。
- 五 block：Qwen2 M128 已有27项限定模型门禁通过；其他四个未新增完整 M128。完整 block RTL 0/5，1024/1224未启动。固定4096 MAC全 block 周期口径下无RTL利用率实测，80%/90%目标未验收。
- 本批不含权重、local.npz/remote.npz、生成物、系统工具链/头文件/库路径版本清单；相关待批准内容不因本批而获准上传。


## 2026-10-18 02:50 UTC：保存真实绑定与 resident/N0 源码

- done：十二文件纯项目源码小片 development_snapshots/canonical_host_bridge_source_20261018；8头中1项逐字、7项仅10行include逻辑重定位，包内反投影保持原SHA，隔离31+31源码冷检查通过。外部模型/库/工具头未附，不是独立可编译闭包。无环境路径、工具链清单、生成物或权重。
- done：真实GeneratedBinding v2单probe编译2.512s通过；N0/resident双头probe编译3.732s通过，后者实际独审已确认。函数未运行，旧probe不包含新shared-edge头。
- done：同一最大Host TU从-Os120s中断改独立-O0 profile后7.355s实际完成。Top56对象中截至本快照33项已完成独审；batch5新增8项实际完成待审，累计保存41/56。原Top整体codegen FAIL和缺hier.mk仍保留，显式逐TU编译不冒原make工程通过。
- done：三个child代表TU和一个verilated runtime TU原flags实际编译通过并独审。只是对象资格，不是库、链接或模型运行。
- ongoing：N0真实B退休→同一HostMemory SSA→回复fence→completion0 ACK源码已审；resident/loan子域已审。shared-edge一个low/high eval源码已审，尚未编译新头。PC1真实QKV reduction采用DenseDownOwner burstWrites经DMA streamWrite，不能套N0 MemoryHub写回链；正在实现独立观察。完整PhysicalObserver11总方法仍未闭合。
- todo：余Top对象、全child/runtime、精确对象依赖复用、链接、真实读值与reset/settle验证、全部17owner/21completion/27capture、同冻结M128完整RTL数值与周期回放。
- 五block不新增验收：Qwen2 M128为27项限定模型门禁；其余四个无新增完整M128；完整block RTL仍0/5，更长序列未开始，固定4096 MAC完整block分母的80%/90%仍无RTL实测。
- 系统工具链/头文件/库路径版本hash清单公开许可仍独立待答，本批不含该类内容，不改变许可状态。


## 2026-10-18 06:00 UTC：真实启动与首个M128业务诊断的源码保存

- done：14文件纯项目SOURCE小片 development_snapshots/canonical_host_pc0_startup_source_20261018。11源码中5逐字、6仅9行include逻辑重定位；隔离30+30检查通过。controls不发布；无系统路径/工具链清单/原receipt/rawlog/真实handle地址/权重/生成物。不是独立构建闭包。
- done：全部192对象（Top56 O0、child133和runtime3原flags）独立核验，三库192成员字节/顺序/索引实际归档通过。新startup TU编译链接通过，固定nojob20eval真实执行通过：8不同handle、各combo12/seq4/ignored4/final1、reset三子计数各1、总DPI184。只该启动窗口，不代表业务数值或普遍settle。
- ongoing：原M128完整14+2输入已实际加载并核16RAM哈希，PC0真实执行触300秒工作上限，原NOT_COMPLETED保留。末保存采样598016完整周期，无保存ACK0/输出数组/数值结果；非准确最终周期。write_bytes=0为owner结果完成累计，不是实时B/store统计，不能推断无写。
- done：源码与实际生成物独核归约下界2428928拍（较弱2018304亦成立），原2M诊断cap不足以完成正常128行N0，单加wall无效。该事实不证明原现场无停滞/OOM，也不能把模拟器wall当硬件性能。
- ongoing：最小进度探针仅读取既有29状态、8真实pre握手、4高沿状态变化，不加eval/改RTL。60秒含加载/最多200k完整周期，仅诊断窗口；新trace TU已编译链接，actual独审进行中，未执行trace。
- ongoing：完整block观察源码PC0–15已分域有限SOURCE审查；resident16–18窄修在审、Down19 prefix和末Add20仍待闭合。27数组导出、ActualCoverageVerifier及独立参考集成不完整，SOURCE不得冒实际通过。
- 五block不新增验收：Qwen2 M128保持27项限定模型门禁；其它四个未新增完整M128，完整block RTL0/5、更长序列未开始。固定4096MAC/完整block分母的80%/90%仍无RTL实测。
- 原Top codegen FAIL、Os编译超时、缺hier.mk等历史不改；后续各独立对象/归档/链接/启动资格按真实范围记录。环境清单公开许可仍待答，本次无此类内容。


## 2026-10-18 08:00 UTC：断连后的固定源码恢复与可重组装小闭环

- ongoing（原运行终态未知）：约07:44 UTC执行环境连接中断，原N0会话74562随后不可查询。最后已读取的真实进度为row28、cycle646947、B2688及ACK172032B；这是最后观测，不是断连时的精确最终状态。没有取得该次ACK0、完整N0数组或数值比较终态，不能追认PASS，也不能把连接故障称作模型数值失败。
- done（恢复后新核验）：从远端固定9b2ea5490c5d01870d1b8d953f3dad83cd245c9e恢复项目源码，五组已发布snapshot共55文件逐Git blob核验一致，normal/-O重新实跑各115项SOURCE冷测。旧执行资产及未发布full27实现未随恢复工作区保留；历史审阅记录不能代替当前缺失文件或运行资格。
- done（新的纯源码复现片）：新增development_snapshots/canonical_host_source_recovery_20261018/，保存22份已发布原字节源码及有限标准库恢复/校验脚本、中文步骤和仅项目source hash。可从固定仓库重新组装，startup和PC0同名ledger分开保留。当前包及fresh重组装normal/-O各19项通过；冷模块采用同bytes先hash再compile/exec，合法污染pyc负例不会执行缓存代码。首版pyc入口HOLD保持历史，不追认。
- ongoing：37条literal quoted include中20条在新源码组合内解析，17次引用仍缺9个名字：3份项目实现、4个生成模型头和2个外部runtime头。当前不能独立编译Host，不能用stub、旧自造权重oracle或额外eval的测试台补成canonical闭包。恢复脚本、hash和合成hold测试不证明C++/RTL行为或full27数值。
- todo：先逐小片补齐有明确来源的项目端口、同RAM/SSA与加载契约；对找不到原件的实现作为新代码重新审查并及时保存。真实生成模型/工具链及新编译/链接/运行需要各自独立有界门；本批没有启动大EDA或模型运行。原进程不能从row28续跑。
- 五block仍不新增验收：完整block RTL保持0/5，17owner/21completion/27capture的实际完整证据和固定4096MAC全block周期口径下80%/90%利用率均未完成。本次仅项目源码及说明，不含权重、原输入/参考、生成模型、二进制、原进程日志或系统工具链环境清单。


### 2026-10-18 08:20 UTC：恢复后首个实际项目接口源码片

- done：新增独立 HostPins 源码，复用已发布的 54 个输入清零赋值，并读取 4 个 result 字段和 4 个 hub 计数；源码与原 Scala/已发布调用字段对应。
- done：最小同字节 SHA-256 校验后 compile/exec 冷入口，拒绝改源并忽略合法 timestamp 污染 pyc；正常与 -O 各 15 项通过，独立审查关闭入口和来源身份问题。
- ongoing：从原 fixture/编码器源码恢复 metadata-only 可复放入口；布局证据仍不构成 resident Gate/Up DDR 写权限，旧输入流 framing 尚未恢复。
- todo：补齐真实 launch、RAM/B 退休/SSA 以及完整加载封存语义，再建立真实生成模型依赖。当前片尚未实例化 C++ 模板或验证生成端口 ABI，不能编译/运行完整 Host。
- 边界：旧 session 74562 终态未知和未发布 full27 丢失事实不变；完整 block RTL 仍为 0/5，不提升数值或利用率结论。


### 2026-10-18 08:30 UTC：原 M128 metadata-only 可复放源码

- done：调用 8 个已固定原项目模块，以同一源码 bytes 校验后执行；真实 sys.path 不变，不加载 NumPy/Torch。独立正常与 -O 各 11 项冷测通过。
- done：fresh 重放生成 21 条命令和 215 个描述符，两表分别 384/3456 字节；35 个 reservation、2 个 KV 子视图、4 个 region 与固定源码布局逐项吻合。
- done：发布仅 10 件可再生源码与项目身份摘要，不含四件生成物；测试在没有 generated 目录时临时生成并核对原大小/SHA。
- ongoing：恢复实际 same-RAM 初始化、封存与后续加载连接。94,920,448 字节仅为 14 个只读tensor及两表的布局和，不是已生成、读取或验证的 tensor payload。
- todo：真实加载协议、数据来源验证及B退休/SSA仍待实现；旧 wire framing、launch、resident DDR 权限、完整 Host 与27数值资格均未恢复。旧 N0 会话终态未知和完整 block RTL 0/5 保持。


### 2026-10-18 09:04 UTC：真实 C++ 小 RAM 行为恢复

- done：独立连续 RAM primitive 实现输入白名单、初始化掩码、整块预检、覆盖封存、只读视图和永久 poison；v2 深拷贝元数据，修复 caller 保留 vector 元素别名可缩小覆盖要求的问题。
- done：真实单 TU 合成行为测试完成 190 个断言（51 个 check、139 个 rejected，不是 190 个独立 case），包含旧 v1 无 UB 漏洞正控及 v2 拒绝、长字符串/元素引用修改与销毁、越界/重复/欠初始化/部分失败原子性/封存后写。
- done：同一实际 allocation 的只读视图读回 24 字节合成数据，Python SHA-256 与独立固定向量吻合。该 hash 不是 canonical 输入身份，测试未执行模型或 RTL。
- done：发布生产头、明确标注的 v1 回归正控、真实测试 TU 和可搬迁复现脚本；无 ELF、系统身份库存或完整运行日志。执行时仍动态计算 compiler 身份，留在调用者本地结果。可搬迁脚本 10+10 mock 通过，其本身未重复 native。
- ongoing：按已发布原始模型/provider 身份恢复 same-buffer 加载连接；真实 payload 仍需按需获取/验证，不猜旧 framing。
- todo：canonical digest/EOF/receipt、真实 HostMemory/B 退休/SSA/prefix 和完整 27 采集仍待新证据。旧 session 74562 终态未知、完整 block RTL 0/5 保持。


### 2026-10-18 09:14 UTC：固定原始输入与 provider 预期身份恢复

- done：从 7 个已发布来源固定 13 份 raw BF16 输入与 14 个 M128 provider 的名称、形状、大小、转换后 SHA-256，以及两张 metadata 表的预期身份；只读校验不导入 producer 或数值库。
- done：14 provider 名称/大小与恢复布局逐项一致，合计 94,916,608 字节；加两表 3,840 字节为 94,920,448 字节。正常与 -O 各 11 项冷测及 verify 双模式通过。
- 边界：这些是已发布历史输入身份，不是当前 payload 重新读取或数值验收。当前缺失 13 raw tensor；原 producer 依赖的 work 元数据未恢复。不得从旧 stream SHA 或长度反推 framing。
- ongoing：新逐输入流接口将实际写入同 RAM，固定 expected 摘要先校验，再封存与同 RAM 重算；仅固定交接边界哈希，正常只读访问不全量重算。
- todo：取得并验证真实原始 payload 后才能授予 canonical 加载身份；launch、完整 Host/27 数值和旧 N0 终态未知边界保持，完整 block RTL 仍为 0/5。


### 2026-10-18 09:29 UTC：逐输入同 RAM 加载器真实合成行为闭环

- done：新增标准 SHA-256 与逐输入 C++17 loader，固定名称/顺序/长度/摘要、64 KiB 分块和严格 EOF；可信 expected 元数据深拷贝，异常粘性 poison。
- done：同一实际 RAM 在封存和一次性 token 兑换前分别复核 SHA；只读 view 显式 reverify，正常读取不逐 beat 全量哈希。未知 allocator 测试形态在读取探针前安全拒绝。
- done：真实单 TU 编译 1.393817 秒、测试 0.127493 秒，421 次 check 调用通过（不是 421 个独立 case）；最大声明合成 RAM payload 为 65,537 字节，并有等长初始化 mask。三个受监督阶段均退出 0 且保存锚定清理证据。复现脚本普通/-O 各 15 项 mock 冷测通过。
- 发布范围：仅生产头、测试、复现脚本、项目 pins 与必要数值摘要；不包含 ELF、当前编译器路径或二进制身份清单、完整运行日志。保留未来执行时写入本地 receipt 的动态 compiler SHA 功能。
- ongoing：按真实 metadata allocation 顺序绑定 14 provider 与两表；保持原地址需约 188.6 MB 连续 RAM，完整四区约 213.5 MB，初始化 mask 另占同等容量，不能把 94,920,448 字节 payload 合计当作分配量。
- todo：真实 raw payload 获取/逐 hash 校验与 canonical 加载仍待单独授权和预算；历史 framing、生产 HostMemory/launch/27 数值均未恢复。旧 N0 终态未知，完整 block RTL 仍为 0/5。


### 2026-10-18 09:38 UTC：canonical16 固定同 RAM 输入绑定源码

- done：新增无参数 make_canonical16_loader() 固定 factory，明确 commands/descriptors 后按原 metadata readonly allocation 顺序放置14个 provider；gamma0=index9、x=index15。逐项固定原地址、长度和SHA，禁止 caller 覆盖 expected/地址/预算。
- done：两路源码独核16项与35reservation/四region及真实已发布commit/blob相符；普通/-O各10项冷测与verify双模式通过，三个依赖头原样保留。
- 容量：完整四区单数组213,473,600字节，payload与初始化mask两数组426,947,200字节；16输入总计94,920,448字节，其余118,553,152字节不属于初始化白名单。未调用factory或进行大RAM分配。
- ongoing：恢复真实payload的按需获取与精确hash验证方案；未来实际大输入另核AS1GiB及全部运行开销，禁止沿用合成小测试256MiB预算。
- todo：本片只固定SOURCE绑定，未建立HostMemory输出/DDR权限、B退休或launch准入；真实canonical加载/数值/完整Host27仍待验证。旧N0终态未知，完整block RTL仍为0/5。


### 2026-10-18 10:16 UTC：原始 BF16 切片恢复与下载复现源码

- done：经默认平台运输通路，从官方 Qwen/Qwen2-1.5B-Instruct 固定 revision ba1cf1846d7df0a0591d6c00649f57e798519da8 获取所需13份BF16切片，共94,382,080字节；仅embedding前256行和layer0相关张量，没有获取整模型。
- done：22段与13完整文件共35份实际SHA/长度全部匹配冻结身份，13次拼接逐字节一致，22份精确206/Range回执独立核验通过。真实payload只留本地；发布仅下载源码、固定范围/project pins、冷测与必要安全计数摘要。
- done：默认平台代理委托保持，无直接连接fallback、应用凭据设置或代理值记录；23项原检查加运输边界测试普通/-O各24项通过。900秒共享/socket90秒/缓存256MiB限额和失败保全源码保留。
- 历史：首次显式无代理尝试以URLError失败，具体reason未保存；后继默认平台小API与raw获取成功不能反推原错误原因。被拒的双路诊断无原终态报告，未知保持，不追认。
- ongoing：从已核raw13按原公式生成14个provider并逐项匹配旧SHA，尤其BF16转置、FP32位扩展与RoPE libm结果；expected不变，实际转换仍待源码审及首次预算执行。
- todo：本次只恢复原始输入，没有执行canonical loader、Host或RTL；完整Host27与旧N0终态未知边界保持，完整block RTL仍为0/5。


### 2026-10-18 10:31 UTC：14 provider 实际字节身份重建

- done：从已验证raw13生成14个provider，共94,916,608字节，全部匹配冻结旧SHA；7矩阵保持BF16转置，norm/bias/x按原位映射扩展FP32LE，RoPE按原double公式与1024容量padding生成，旧expected未修改。
- done：同一已hash raw私有buffer供转换；每项临时文件写完后完整SHA和回读通过才无覆盖提交，14项全过才发布PROVIDERS完成报告。实际进程原session40791终态exit0，未使用reference payload、网络或native模型。
- done：普通/-O各18项小测试与SOURCE独审通过；发布仅转换源码、固定原公式/身份规格、project pins和安全计数摘要，真实14个provider文件只留本地，不提交或编码入源码。
- ongoing：把原两张metadata表与14个真实provider按canonical16原顺序送入C++同RAM加载器，核stream/封存/token/view四遍实际摘要；首次完整RAM加载门待SOURCE审，尚未执行。
- todo：provider字节身份不授予HostMemory输出权限、launch、完整Host27或RTL数值资格；旧N0终态未知保持，完整block RTL仍为0/5。


### 2026-10-18 10:45 UTC：真实 canonical16 同 RAM 输入加载复现源码

- done：14 个真实 provider 加两份固定 metadata 表共 16 输入，94,920,448 B，已在同一 213,473,600 B RAM arena 按原白名单加载；严格 EOF、覆盖封存、一次 token 兑换及实际 const span SHA 全部匹配固定身份。
- done：本次单 TU 编译、metadata 重放、加载均退出 0；加载阶段记录 14.692706 秒（含监督收尾，不作为纯性能或峰值内存测量）。四遍 SHA 共 379,681,792 B；该结果仅授输入加载。
- done：保存 21 件纯源码、项目相对身份、18+18 冷测摘要及安全实际数值摘要；不提交 ELF、权重、生成 metadata、完整日志或系统身份库存。实际 payload 仍按需在本地/CI 生成。
- ongoing：恢复 HostMemory 的同 allocation runtime 能力、业务可写区域、成功 B 响应后的原子写入和初始化 mask 接线；现有 RO 输入 view 不授写权限或 launch。
- todo：原生成 RTL/工具链需独立重建，Host/AXI/DPI/完整 27 数值尚未恢复；07:44 丢失前 N0 会话 74562 的终态仍未知，完整 block 验收仍为 0/5。


### 2026-10-18 11:26 UTC：隔离 runtime RAM 小闭环源码与真实合成测试

- done：新隔离 runtime kernel 使用同一 payload allocation 与初始化 mask，固定四区/具体 allocation 权限，首片只接受 N0 写路径；RO 输入、guard、保留尾及未授权区域拒绝写入。旧真实 canonical16 consumer 原件保留。
- done：私有退休 adapter 将 AW/W 暂存与成功 B 提交分开；全事务检查后再无异常修改 payload+mask，completion 发布前继续拒绝输出读取。生产模型/scheduler 尚未绑定，不把测试授权等同实际 owner 事件。
- done：真实 C++ O0/O2 两配置各 186 check 调用结果相同，4 个 private API 负编译均实际退出 1 并命中对应诊断；不是 372 个独立案例。9 stage 依原预算串行完成并保存清理证明。最大合成 arena 1024 B。
- done：保存 22 件纯源码、复现 runner/冷测和安全摘要，未来运行时编译器 SHA 记录能力保留；不提交 ELF、当前系统身份、完整日志或 payload。旧 source v2 汇总字节误差只在新投影中更正，未改旧资产。
- ongoing：补固定 launch_payload 与唯一 scheduler 下 N0 retirement 真实字段接线，仍保持 adapter_runtime_bound=false；并行只读盘点生成接口/工具闭包，重建须另门。
- todo：新版 runtime 尚未进行真实 canonical 大输入/Host 验证；07:44 丢失前 N0 会话 74562 终态未知、完整 27 采集未恢复，完整 block 验收仍 0/5。


### 2026-10-18 12:00 UTC：固定 launch 与 N0 字段接线小测试复现源码

- done：新增固定 launch 23 字段、真实 56-bit completion 位域解码，以及 81 个读取/83 个来源别名的字段接线源码。epoch 来自已接受 launch，owner tag 来自已接受 job；AXI ID 只在实际 AW fire 路径首次锁定，不杜撰缺失端口。
- done：单 O0 tiny C++ fixture 真实执行 436 次断言（218 payload、218 私有调度 fixture），覆盖 launch 身份保存、AW 停顿/首次 ID、B 原子提交、错误 completion 及同 RAM 发布后读取；编译/运行均退出 0，原清理证据完整。
- done：其中 core/hub/DMA/响应/done 事件由明确 test-only fixture 注入；该测试不证明实际生成模型产生这些事件。modelbinding、actual_n0_execution、adapter_runtime_bound、canonical_input_sha_verified、full_host_ready、launch_ready、eda_executed 七项均 false。
- done：保存 29 件纯源码/测试/复现脚本/安全摘要，未来运行时 compiler SHA 核验保留；不提交 ELF、机器身份清单、完整日志、生成 metadata 或 tensor。两个缺生成头的探针未执行，仍为 PENDING。
- ongoing：按生产 92 源加新共同 Host emitter 形成新 93 源闭包；87 JAR 锁集与20 HardFloat的获取/源重放脚本正在有限审，尚未下载/编译，旧95身份不继承。
- todo：真实 generated ABI、reset、唯一实例、resident-before-N0 准入与完整27采集仍缺；07:44 丢失前旧 N0 会话74562终态未知，完整 block 验收仍0/5。


### 2026-10-18 12:15 UTC：Host-only 新93源与固定官方依赖复现方案

- done：保存19件纯源码/计划/冷测：以111项项目来源固定生产92源重放和tap修补，再加入新共同Host emitter形成新的93源身份；不混用丢失的旧95源/类/IR资格。
- done：固定87 JAR锁集、20 HardFloat源码及后续工具的官方来源/版本/SHA；获取器默认沿平台运输路径，严格逐件校验、原子发布、失败保留已验证部分缓存，无自动重试或应用路由备用。依赖下载字节不进入Git。
- done：来源冷测普通/优化各17项、获取冷测各34项通过；独立三项回归关闭源码缓存加载、失败清理/终态冲突及超时读取计账问题。发布投影仅删除过期字节数文案，执行源码与已审版本相同。
- ongoing：JAR87与HardFloat20的外层有界获取门另审；两组分别最多1200秒/300秒，单CPU、AS512MiB、单文件64MiB，默认平台环境不变。此处仅复现方案，尚未取得依赖或完成源组装/编译。
- todo：获取后需核实际逐件身份，再进行fresh Host93源组装与有界class编译；firtool、Verilator、iDMA及生成接口按对应阶段独立核验，不能凭来源计划授执行或模型资格。
- todo：真实Host ABI/reset/唯一实例/resident准入与完整27仍缺；07:44丢失前旧N0会话74562终态未知，完整block仍0/5。


### 2026-10-18 12:53 UTC：固定依赖与新93实际恢复、首次CLASS工作窗失败

- done：87个固定官方JAR逐SHA取得61,870,159B，20个HardFloat源码取得149,157B；两次串行实际outer分别退出0、316.976秒/88.025秒，原锚清理与完整库存独审通过。未执行下载JAR、未提交依赖数据。
- done：fresh新93源实际组装为1,002,844B，outer退出0、1.809秒，三tap/新共同Host emitter和111项目来源/HF20精确身份独审通过；旧95资格不继承。
- done：首次CLASS按单CPU/heap1GiB/AS4GiB、150秒总窗/120秒工作窗执行，约120秒compile_stop触发TimeoutError；outer121.697秒退出1，0B编译日志、0class。清理使用原锚后SIGKILL/reap -9，不是Java自然退出。
- done：原handler文案absolute150s和timed_out=false均不改变实际工作窗超时事实；成功postflight未运行，独立现时93/87输入重核通过不倒填原后验。没有CPU/RSS采样，不能由空日志推断OOM或具体编译阶段。
- done：保存23件纯复现源码/测试/安全摘要，三个执行入口代码不改；portable纯mock普通/优化各34项通过。排除本地路径绑定、机器身份清单、日志、JAR、class和生成源码树。原失败现场保留，无自动重试。
- ongoing：先以同Java/AS/heap/CPU的两个极小版本启动探针补真实CPU/RSS与启动证据，各子工作不超过10秒；未据此授CLASS或RTL资格。
- todo：须先诊断并另核有界CLASS后继，随后才是CHIRRTL/SV/真实ABI/Host运行；旧N0会话终态未知、完整27尚缺、完整block仍0/5。


### 2026-10-18 13:22 UTC：启动实际核验与可观测CLASS校准源码持久化

- done：同Java/heap1GiB/AS4GiB/单CPU的Java与Scala版本入口分别outer退出0、0.323秒/2.433秒，固定版本21.0.12.1/2.13.16与87项classpath身份、原锚清理独审通过。
- done：两个专用child全生命周期实际user/system CPU分别0.043504/0.099344秒与1.347912/0.412372秒，绝对峰值RSS为28,612/90,604KiB，含preexec；这些观测不回填旧CLASS编译阶段或峰值。
- done：保存13件纯源码与冷测/公开官方来源依据，8件执行相关原件逐字继承。startup安全摘要已有实际审；校准摘要保留冻结时PENDING/null，不热改历史候选。
- done：新校准门只增无去优化作用的-verbose、每秒原leader身份核验CPU/RSS/HWM日志及终态getrusage；原WNOWAIT清理保持。330秒总窗/最多300秒compile、heap1GiB/AS4GiB/单CPU，普通/优化各23项纯mock通过。
- ongoing：一次新校准已保存outer退出0、279.264秒和562个class/9,653,495B，当前交独立实际库存与资源审；此处先记录原执行观察，尚不以源码包或孤立RESULT授CLASS资格。
- todo：独审后再规划CHIRRTL、SV和真实Host接口恢复；verbose仅保证已发进度逐行flush，不保证每phase或日志必在2MiB内。旧120秒FAIL保留，07:44丢失前N0终态未知，完整block仍0/5。


### 2026-10-18 13:55 UTC：新Host93 CLASS与CHIRRTL实际库存闭合

- done：有观测CLASS单次校准outer退出0、279.264秒，固定93源/87JAR生成562类、9,653,495B，完整748文件及输入后验独审通过；保留原120秒FAIL。
- done：实际child全生命周期CPU269.037274+7.914993秒，绝对峰值RSS946,504KiB；274条leader采样原值保留，包括一次VmHWM小幅下降，不宣称采样序列严格单调或倒填旧失败原因。
- done：同一新共同Host emitter实际生成HostBlockCollection.fir，42,417,256B、SHA256为264f8b3a11c02d0d0917001f1d69452ec1c1294c426c9c81e1e577cdc523385a；outer退出0、47.114秒，完整657文件/246目录/114,100,740B独审通过。仅CHIRRTL生成库存资格。
- done：发射实际child CPU40.13349+4.498979秒，绝对峰值RSS621,448KiB；保锚清理与原562类/87JAR后验闭合。实际5条索引宽度warning原文保存，有限源行解释不能证明全过程索引安全。
- done：保存9件纯发射源码/冷测/项目class相对名大小哈希/安全说明，无class、JAR、FIR内容或机器库存。包内安全历史保留冻结时实际审PENDING，不热改原件；当前实际审结论在本计划追加记录。
- ongoing：同一FIR的83口/8endpoint/metadata/九tap结构资格仍未闭合；初版checker遗漏invalidate覆写的反例已确认，隔离窄修后再只读核，不修改或重新发射FIR。
- todo：结构闭合后才进入独立firtool/SV门、真实ABI与Host执行；本次未运行firtool/Verilator/Host，旧N0终态未知，完整block仍0/5。

### 2026-10-18 14:36 UTC：同一 Host93 CHIRRTL 有限静态结构闭合

- done：保留原 42,417,256 B FIR（SHA-256 `264f8b3a11c02d0d0917001f1d69452ec1c1294c426c9c81e1e577cdc523385a`），未重发射。前两次只读检查分别因 checker 的 primitive 同名引用和 aggregate flip 投影缺口返回 INCOMPLETE，原失败记录保持。
- done：最终 checker 仅按固定 metadata 类型展开所查叶，正/反向 ready/valid、schema/flip、覆盖与 invalidate 负例均核；22+22 checker 冷测及 14+14 包装冷测通过，SOURCE 独审 `018d373a…`。
- done：第三次原会话实际 exit 0、外层 8.833 秒；限定 actual 独审 `9364010b3d9008065a85ba7ed77c1f5a31cc86f8b471f687a7b2c9530a47cd1e`。原 657 件生成库存和两次失败未变。
- done：静态报告为 Host 子树 690 个实例、共同 collection 699 个实例及 699 个定义（均含各自根，口径分列）；83 口（39 入/44 出）、8 endpoint、8 clock gate、1 iDMA backend、8 条 metadata 请求/响应静态直连、9 个 tap bundle 共 2604 bit。
- done：持久化 12 件纯源码/正负测试/安全摘要；不含 FIR、class、JAR、ELF、完整日志或机器环境库存。包中历史摘要的第三次 actual 审 PENDING 是冻结时状态，本条记录后续独审结论。
- ongoing：按固定官方 firtool 1.62.1 准备必要包获取与同 FIR 的 SV 转换门，先核 archive/member 原 SHA；未执行 firtool，未重建 Verilator。
- todo：后续 SV/生成 C++、真实接口绑定、Host 执行与数值验收仍须各自实际证据。此静态结构审不证明协议行为、算术、tap 事件语义或无组合环；07:44 丢失的旧 N0 会话终态仍未知，完整 block 保持 0/5。

### 2026-10-18 14:58 UTC：固定官方 firtool 包及唯一成员恢复

- done：沿官方 Maven 默认平台通路取得固定 llvm-firtool 1.62.1 linux-x64 包，archive 为 8,763,451 B，SHA-256 `63acdcb58ed12d4c1aa0ecdedc6e2425a252e94eefb75df9253c118d7d222039`；无自动重试。
- done：同一已核 archive buffer 内仅提取 allowlist 的 firtool 成员，25,009,456 B，SHA-256 `7f52d2a3782d09736895f66e7eb0e5cc4b3b1b18aa1ad0d04fca4cd6e42cd2ee`，保存权限 0600，未执行该二进制。
- done：SOURCE 独审 `48e43cd6…`，24+24 tiny/mock 通过；原单次外层 exit 0、5.827 秒，在 180 秒共享上限内。保存原锚定清理、独立退出与失败保全合同，不以孤立非终态 receipt 认定成功。
- done：限定 actual 审 `2fc8626ab6bf2b86d2243f5a207984456935cdf7b579b6053e4f8e0663fba8ae` 核对 11 件/33,807,081 B 库存、原输入、archive/member 实际 SHA 与 ZIP 唯一路径，结论仅固定工具字节身份。
- done：持久化 10 件获取/单成员校验纯源码、测试、计划与安全摘要；无实际 archive、binary、完整日志或当前机器库存。包内 actual 审 PENDING 为原冻结事实，本条另记后续审结。
- ongoing：同一已审 Host93 FIR 的有界 SV 转换门正绑定新工具实际身份；首次预算 180 秒总/150 秒工具、单核/AS 2 GiB/FSIZE 128 MiB，未执行前不授 SV 产物资格。
- todo：SV 结构、生成 C++、真实 Host 接口与数值回放均待后续实际证据；不提前重建 Verilator 或 iDMA。旧 N0 终态未知与完整 block 0/5 保持。

### 2026-10-18 15:13 UTC：首轮同 FIR SV 转换超时，保留失败并冻结复现源码

- done：固定 Host93 FIR `264f8b3a…` 与官方 firtool 1.62.1 成员 `7f52d2a3…`，经实际绑定 SOURCE 独审 `301a4e84…` 后进行唯一首轮转换，未关闭任何检查。
- done：原会话外层 exit 1、150.983 秒；工具工作窗明确触发 `TimeoutError: SV firtool_work150s deadline`，保锚清理后 reap -9/group absent，不能将清理退出码称为自然工具退出。
- done：保存 147 条同 PID/starttime 的逐秒 leader 样本，末累计 CPU 147.80 秒；回收 child CPU 144.053441+4.533091 秒、绝对峰值 725172 KiB。原 VmHWM 有一次 48 KiB 下降，保留原值且原因未知。
- done：verbose 最后开始 `firrtl-check-comb-loops` 而未报告该 pass 完成；SV 文件 0 B，无 annotation/成功 RESULT，不能据此推断存在组合环或 OOM。原成功后验路径未执行。
- done：失败 actual 独审 `80f63b2bcad35941eadd57c781ca19628e86c20871ce84e8472fd616f582a828` 核对 9 件/67,494,439 B；当前原 657 件生成及 11 件获取库存与 FIR/tool 重 hash 相符，明确属于独立现时核验。
- done：持久化 10 件未绑定纯源码/测试/安全失败摘要；计划去除本机绝对路径，PENDING 在输出前拒绝，后续真实绑定必须另行冻结审查。无 FIR/SV/binary、完整日志或机器库存；摘要 actual 审 PENDING 为冻结事实，本条另记后续审结。
- ongoing：根据本次持续 CPU/稳定 RSS 准备单次 390 秒总/360 秒工具、CPU360 与每秒 400 条上限的有观测校准；原 AS2GiB/FSIZE128MiB/flags 不变，SOURCE 闭合前不执行，不跳过 comb-loop。
- todo：历史 95.9095 秒来自不同 Bench FIR `db430673…`，不能保证当前 Host 耗时；若再次超时先定位该 pass 源码复杂度，不继续盲目加时。SV/Host/数值资格均未取得，完整 block 保持 0/5。

### 2026-10-18 15:32 UTC：同 FIR 有观测校准完成 SV 生成，结构与运行仍待验证

- done：保持原 Host93 FIR、firtool 成员、三个生成 flags、CPU 单核、AS2GiB 和 FSIZE128MiB，唯一校准将总/工具/CPU 预算调为 390/360/360 秒，逐秒无追赶采样上限调为 400；SOURCE 独审 `7f212c43…` 闭合后执行。
- done：原会话外层 exit 0、269.915 秒，工具自然退出 0、监督阶段 267.963335 秒，保锚清理和成功后验完成；生成 SV 76,366,612 B，SHA256 `2fcc1ba70ad3406b967292624329593aa38e3fe562e9ff3ac675eec100562f61`。
- done：工具日志记录 comb-loop 检查完成 143.182 秒、export-verilog 完成 18.491 秒；这些是日志阶段观察，不是独立性能基准。whole-child user/system CPU 为 261.502381/5.708136 秒，绝对峰值 1,106,840 KiB。
- done：265 条采样保留三处 VmHWM 下降原值，不平滑或推断其原因。原 150 秒失败、其全部输出与旁件保留，不以本次成功改写历史。
- done：actual 独审 `b170f06c47d83c3dfd75e5f83962168aad16765305e2292f54ae9d30a0a5cc46` 核对 4,141 项/65 输入、10 件/143,917,023 B；原 657 件生成库存、11 件工具获取库存及首次失败全未变。
- done：持久化 10 件纯源码、测试及安全摘要，模板未绑定时在输出前拒绝；冻结摘要中的 actual 审 PENDING 保留，本条另记后续审结。不提交 SV、FIR、binary、完整日志或机器环境库存。
- ongoing：在同一实际 SV 上核 83 口、8 endpoint、DPI 与观察信号；方向/位宽续行按真实语法最窄支持，尚未取得 SV 结构资格，不重复转换。
- todo：生成 C++、真实 Host 接口与数值回放仍缺，Verilator/iDMA 仅准备最小恢复计划，未启动长 RTL。旧 N0 终态未知、完整 block 0/5 保持。

### 2026-10-18 21:09 UTC：同一实际 SV 有限静态审闭合，保存两次检查失败

- done：首轮同 SV 检查遇双 packed 非 tap 声明形状，原 exit 1/5.436 秒；第二轮在主 tap 精确清单断言失败，原 exit 1/7.352 秒。两次均为有限 checker 不支持/分类问题，未据此认定 RTL 非法，原失败完整保留。
- done：按实际声明最窄支持固定双 packed wire，并拒顶层逗号隐藏声明；原 75 主 tap 合同不变，精确独立记录 28 个 Cos/Sin 拼接辅助 wire 和 2 个末级 root，核 30 个有序二元文本拼接。字符串吞除和保留根 ANSI 同名两项审计反例在 v6 关闭。
- done：v6 SOURCE 独审 `ac1113fa…`、checker 30+30 与包装 14+14 冷测通过后，唯一第三轮只读检查原会话 exit 0/2.879 秒，SV 原 SHA256 `2fcc1ba70ad3406b967292624329593aa38e3fe562e9ff3ac675eec100562f61` 不变。
- done：actual 独审 `651f2c3474e197b85432c544d5e0bff6cc94145df37d3c9e456a3bf6c60c7708` 核对 654 项/103 输入；唯一静态证据 38,724 B，原生成 10 件、两次同 SV 失败及首次 150 秒 firtool 失败均未变。
- done：限定静态报告分别记录 59 个 SV 定义、Host 子图 758 实例和 collection 767 实例（含生成 memory）；83 个 Host 口、8 endpoint/8 gate/1 backend、9 bundle/75 主叶/2604 bit。28 辅助声明总 3072 bit 单列，不重复计入主观察位数。
- done：持久化 15 件纯源码/测试/安全摘要，其中 3 份人工 tiny 反例由固定空模块图和常量连接合成，没有复制真实 SV 或张量；四 Python 执行/测试原字节，重定位 30+30/14+14 通过。冻结安全史的 actual 审 PENDING 保留，本条另记审结。
- ongoing：恢复固定官方 Verilator 层级替换修复源码及最小工具依赖，重新证明 micro 的 hierarchy/DPI/多 handle；旧 5.032 deb 和已丢失的局部补丁不能继承正确性。
- todo：完整 metadata 反投影、外部端口宽度、tap 驱动/事件语义、生成 C++ 与 DPI 链接、真实 Host 运行/数值仍待独立证据。旧 N0 终态未知，完整 block 0/5 保持；本批不提交真实 SV、工具 binary、张量、完整日志或机器环境库存。

### 2026-10-18 21:37 UTC：固定官方工具依赖五包获取验收，尚未安装或执行

- done：固定官方 autoconf、m4、flex、libfl-dev、bison 五个包的 URL、长度与 SHA256；同默认平台路径、socket30/no retry、180 秒总/160 秒工作窗进行唯一有界获取。
- done：原会话外层 exit 0/17.480 秒，5 包共 2,466,616 B；保锚清理闭合。actual 独审 `352b1d020121f1530a0fbafd6af72b60eef0fed77b24cb6761e6825b36c1284a` 核对 315 项/58 输入及完整 13 文件/2,504,946 B，仅授固定 opaque bytes。
- done：确认旧 worker 冷入口用 assert 核身份在 -O 下会删除；生产显式 hash 链与已独审实际包字节不受影响。旧审不热改，补充审 `eb9950de…` 限定旧优化冷入口身份资格。
- done：发布 15 件纯源码/公开固定 pins/安全摘要；portable 冷入口改为同 buffer 显式拒绝和调用者 --repo，补坏长度/同长错 SHA/flags 反例，worker 21+21、外层14+14及独立7+7通过。
- done：内容独审 `6312cb1fbc2841a4b1edd7c35d290ddb5596cf5f2dc2876eff63d958612cf865` 核对原生产字节、三个项目依赖、无包体/完整日志/当前机器库存；冻结摘要 actual 审 PENDING 保留，本条另记实际审结。
- ongoing：同资产只读布局已确认标准 ar 与 control/data.tar.xz；下一步仅提取固定 67 regular 文件并生成有明确原件 hash 关系的 staged 配置，之后做 --version 与宏/skeleton 小资格，不泛化安装器。
- ongoing：固定官方 Verilator 修复源码首次下载 child 已完成，父后验因 SOURCE.json 0644 与 0600 要求不符保留失败；将同资产只读复核再资格，不重复下载，不修改原记录。
- todo：工具构建、层级/DPI/多 handle micro 与真实 Host 仿真仍待执行证据。五包尚未解包安装或运行；旧 N0 终态未知、完整 block 0/5 保持。

### 2026-10-18 22:00 UTC：官方工具源码获取失败保留与同资产内容重新核验

- done：固定官方 Verilator commit `4e194cc3ec8e27b18e17f80d7f99c15f984bbdae` 的 473 个选定源文件（11,747,893 B）已按官方 Git tree 的逐文件 blob 身份核验。归档 SHA 仅作为本次观察后的固定身份，不代替官方来源证明。
- done：原获取 child exit 0，但 SOURCE.json 实际 0644 与外层 0600 合同不符，原 outer exit 1/FAIL 原样保留；原成功后验未执行，不倒填成功。
- done：新同资产只读核验 outer exit 0/0.185 s；旧 483 个文件的内容和记录身份未变，精确固定的 SOURCE.json 0644 例外未扩张。独立实际审 `09bb63269e80967dedf42f43a9fab9b20081f1cdc2ec0b2e163388736996268b` 只授选定官方源码内容资格。
- done：后继 producer 源码仅在原收据创建处临时使用 umask 077 并恢复，冷入口隔离 flags 前移；48+48 小型测试及独审通过。原外层仍绑定旧 worker，此后继尚未绑定新的下载执行门。
- done：本批保存 20 件纯源码、固定来源表和安全历史说明；不提交官方源正文、归档、实际收据/日志、机器路径或环境库存。
- ongoing：依赖最小提取、真实版本与资源微例，随后在固定官方源码上有界单核构建；这些资格分别验收，不由源码获取或提取自动继承。
- todo：工具层级/DPI/多 handle 微例、真实生成模型与 Host 同 RAM 输入接线、有限 N0 回放及完整 block 数值核验。
- 边界：本轮没有新增真实 Host/RTL 数值 PASS；原丢失 N0 session74562 终态未知和完整 block 0/5 保持。

### 2026-10-18 22:30 UTC：官方依赖最小提取与五工具版本/资源微例

- done：从已核五个官方包中精确提取 67 个固定成员（3,598,623 B），加派生配置和收据共 69 文件/3,626,135 B；原包逐 hash 保持，目录与文件权限符合约定。
- done：派生 autom4te.cfg 仅四处已核重定位；实际提取 outer exit 0/0.265 s，独立实际审 `2e7883e3172f2b957c18d03a37ce1478fcb0f0c2b2889cbfb82de2d5e72357ce` 仅授暂存数据资格。
- done：autoconf、autom4te、m4、flex、bison 五个真实版本启动及五个人工资源微例串行完成，十个 outer/native 均 exit 0，各 outer 0.139–0.251 s；生成文本/C 未被执行。
- done：十 mode 独立实际审 `bb0c21890f927b719e93f7721c12bf636d266ebb033e4a0313e833696f872edb` 核 755 个输出文件、每份固定工具副本及原暂存数据不变；这些微例不证明完整工具内部资源访问或 Host 行为。
- done：本批拟持久化 14 件纯源码与人工 tiny 测试，公开模板移除本机路径及实际绑定；UNBOUND 前门拒绝执行，未来使用须重新绑定并审核。保留固定原成员与配置转换规则。
- ongoing：固定官方 Verilator 源上的 autoconf/configure/单核优化后端构建，逐阶段保存实际终态、输入和输出身份；构建资源预算为最大额，不保证完成。
- todo：新工具参数化层级、DPI、双 handle 微例，随后恢复真实 Host 回放与数值比较。
- 边界：不提交工具包、生成源码/二进制、完整日志或机器库存；真实 Host/RTL 数值仍无新增 PASS，完整 block 保持 0/5。

### 2026-10-18 22:48 UTC：固定官方工具三阶段构建复现源码

- done：固定官方 473 源文件与已核依赖的 autoconf 实际 outer exit 0/0.736 s，生成 configure 394,180 B；独立实际审 `364e920bb2af6addc7d43c36ef22ebd15425e50b207f5a2f5e551d3a1cb14fe6` 仅授该阶段生成资格。
- done：configure 实际 outer exit 0/5.035 s，557 文件/16,835,102 B，原 545 件完整保留；独立实际审 `611c15baffdff410d9fcbf42e7bf5953b957698906ee70590cfef49ad04c68d6` 仅授该阶段生成资格。
- ongoing：单核 make 优化后端已观察原 session66277 exit 0/429.473 s，生成 verilator_bin 19,076,520 B，SHA256 `cff217bcf9fa4183c68a0f96cf292728ca11ee7ff1e078904ebaa33529a9d2fc`；完整实际产物独审进行中，不预授工具行为或 Host 资格。
- done：本批保存九件纯源码未绑定模板，执行逻辑保持已审版本，真实执行须填实际身份；公开模板的默认 SOURCE inspection 路径仍未绑定，不把其失败误写可运行资格。
- done：冻结包的 make 历史为 RUNNING/PENDING_AT_FREEZE，保持原文；本计划仅追加上述后来观察，不热改已冻结摘要。39+39 冷测为人工/模拟测试。
- 边界：一秒 leader 采样只观察原 make 进程，不能代表 compiler 子树；终态 RUSAGE_CHILDREN 单独记录。3600 秒总预算为最大额，本次实际耗时按原终态报告。
- todo：固定新 binary 实际审后，先做版本、参数化层级、DPI 与两个独立 handle 微例；官方 m_seqnum 未初始化源码风险继续保留，单次微例通过不能证明该风险消失。
- todo：通过小资格后恢复真实 Host 模型构建与数值回放。无真实 Host/RTL 数值新增 PASS，完整 block 0/5；无工具二进制、生成物、完整日志或机器库存进入本批。

### 2026-10-18 23:29 UTC：生成构造初始化的新派生工具源码与有界增量构建

- done：固定官方优化后端构建已独审 `33c4e8ced5c6eeb866fefab35ef23347596bee97d0ac52f4e8003ec19360f354`；新工具版本启动 outer exit 0/0.120 s。该版本资格不外推层级、DPI 或 Host 行为。
- done：原人工 tiny 生成 native exit 0，但后验未识别合法 STEP token `'sh3`，原 outer exit 1/0.252 s 完整保留。后续同资产只读核验 outer exit 0/0.129 s，独审 `230cc4cc633114d3b59c96af42c529a0ab3b086fc495305ae47fceed76a0684b` 仅授生成静态证据；原 38 文件没有 `.a`/`.o`，child archive 只是未来路径。
- done：原官方 `V3ProtectLib.cpp` 与本次生成的同类构造均确认 `m_seqnum` 未初始化而后递增。停止在该已知风险工具上继续 compile/run，不把静态核验或未来单次微例成功当作风险消失。
- done：新派生补丁只在官方 commit `4e194cc3ec8e27b18e17f80d7f99c15f984bbdae` 的第 340 行构造 initializer 增加 `m_seqnum{0}`；原源码 22,417 B/SHA256 `bddc3100c2ce83d7a4fe4656b0ff33cca1be70ea9a8295037c6aea72bc0ec6c1`，派生源码 22,430 B/SHA256 `380f292c6e82ce30cd7c0b3375ac3f2b91e5c1e872a2c733ca6d0490122cf6fb`。这是新派生，不冒称已丢失旧补丁恢复；版权许可头原样保留。
- done：增量门 SOURCE 独审 `6d1109aed1e5bdf59213ae8503302c11517e9c046a6520830a37c6a9f0e69b0b` 闭合。新独立树复用原 929 文件身份，只不复制目标 `.o`、`.d` 与旧 backend，原件不热改；实际日志必须给出目标编译和链接，意外重建保存失败。
- ongoing：唯一派生构建已观察原 outer exit 0/5.442 s，日志记录仅 `V3ProtectLib.cpp` 编译与一次链接；新 backend 19,076,520 B/SHA256 `75dd308bde0b9cb1e64b36a03ba8be38c64c2b59087dd52300fa8b43a107aeb2`。完整实际独审进行中，尚不授新工具执行、micro 或 Host 资格。
- done：本批保存九件纯源码未绑定模板；内容独审 `28b52e1f053e3f5bbe925ab681a49e720048f002ab13a08c4cc7dacf49e70844`，20 个生产函数原字节，19+19 冷测和重定位核验通过。包内 actual 历史保持 `PENDING_AT_FREEZE`，本条只追加后来观察，不热填冻结包。
- 边界：总 900 s、前验 180 s、工具/CPU 600 s、绝对工作最晚 780 s、清理 5 s、总后验至 900 s；CPU1/AS4GiB/FSIZE1GiB，树 768MiB 与日志 1MiB 为软验收界，采样只针对原 leader。最大预算不保证完成。
- todo：派生实际独审后，分别绑定新版本和同 fixture/fresh root 的重新生成；目标类构造唯一 `m_seqnum{0}` 须定域验证，随后才做层级库编译、DPI 与双 handle 隔离微例。无新真实 Host/RTL 数值 PASS，完整 block 0/5；本批不含对象/PCH/二进制、大树、生成 wrapper、日志或机器库存。

### 2026-10-18 23:47 UTC：派生工具构建和版本独审闭合，保存人工层级/DPI 微例源码

- done：唯一构造初始化派生工具实际 outer exit 0/5.442 s，日志确认只重编 `V3ProtectLib.cpp` 与一次链接；完整实际独审 `61a4f6b18e782f8562d76b1fc77cedb22a86a0c225f900633002931b36b6a818` 核原树、fresh 复制、精确单行 patch、输出与保锚清理。新 backend 19,076,520 B/SHA256 `75dd308bde0b9cb1e64b36a03ba8be38c64c2b59087dd52300fa8b43a107aeb2`，仅授派生构建资格。
- done：新派生 backend 的唯一版本启动 outer exit 0/0.123 s；独审 `60fcf5826de40e78db516916616926da77b2ad8b249478fd381000afbf7da022` 只授版本启动。banner 仍是官方 revision 字符串，派生身份以新 binary 与 patch 的固定 hash 区分。
- done：本批保存 14 件纯源码、人工 fixture 和有限构造检查，内容独审 `cdd4d317bf1e5ed4d62c0c6565037ecd1db47710a48e7d529f73e7c6b45738fe` 核 329 项/27 输入；21 个生产函数、初始化合同和两份人工 fixture 原字节，三个已发布支持源按精确相对路径与 hash 引用。
- done：微例冷测 62+62、定域合同 29+29 通过。公开负例为明确人工合成的 281 B 同形 class 文本，不携带真实生成 C++；固定 buffer 身份、隔离 flags、实际 PENDING 前拒和调用者 --repo 边界保持。
- ongoing：新派生工具的唯一生成已观察 outer exit 0/0.241 s，在 fresh work root、同 fixture SHA 下通过真实目标 container 的定域构造初始化 `m_seqnum{0}` 检查；完整实际独审进行中，尚不授编译、运行或 Host 资格。生成、编译、运行仍逐阶段分别绑定，不能用别处字符串或初始化补偿目标构造。
- todo：生成审闭后再确认参数特化、独立叶状态与层级库编译/实际链接，最后执行 DPI scope 与两个独立 handle 的交错状态、单侧 reset 和独立销毁微例。源码中的期望结果不是实际运行证据。
- 边界：四阶段总窗 30/120/300/30 s、工作上限 10/90/240/10 s，原单核资源和保锚清理不变；默认模板仍 UNBOUND，全部实际槽与冻结安全史保持 `PENDING_AT_FREEZE`，本条仅追加已审构建和版本事实。
- 边界：原官方生成失败、同资产只读静态资格及未初始化风险历史完整保留；新补丁不冒称旧补丁恢复。此批不含工具 binary、对象/归档、实际生成 C++、日志或机器库存；无真实 Host/RTL 数值新增 PASS，完整 block 0/5。

### 2026-10-19 00:09 UTC：派生工具固定 tiny 四阶段实际闭合，层级库与双 handle 有限运行通过

- done：派生构建实际审 `61a4f6b18e782f8562d76b1fc77cedb22a86a0c225f900633002931b36b6a818` 与新 backend 版本实际审 `60fcf5826de40e78db516916616926da77b2ad8b249478fd381000afbf7da022` 已闭合；版本 outer exit 0/0.123 s。banner 的官方 revision 不代替派生源码、patch 和 binary 的固定身份。
- done：同两份人工 fixture、fresh work root 的新生成 outer exit 0/0.241 s；实际审 `d214ccf7cec8bb7b80c4fefccb0907f4bedd547188df7ad37c88e54c20e878e0` 核 38 文件/129,537 B、STEP=3 参数特化、独立 protected wrapper 和 top 边界。真实目标 class 内的 field、constructor、唯一 `m_seqnum{0}` 定域通过；旧/新目标 class 仅增加 13 B initializer。整份新 wrapper 是 2,831 B，另有成对 protection hash 变化，不能把此前 2,832 B 人工 positive 当实际产物。
- done：tiny compile outer exit 0/7.250 s；实际审 `fb32a7c17386917d4588e6f36ede2ceb0ea332d470ad04b63fd9856049e337e0` 核 57 文件/3,417,795 B、七次 O0 编译、一次 top 链接。独立 child archive 68,192 B、组合 top archive 136,728 B 与实际对象逐 byte 对应，ELF 900,240 B；层级资格由生成边界、独立归档和实际链接共同支持，不只依赖旗标或未来 archive 路径。
- done：tiny run outer/native 均 exit 0，outer 0.161 s，保锚清理闭合；实际审 `797d17c03028f01e29d9ba0d3430aada7aff852fed4ba86883b25fbe2fa55b72` 仅授固定派生微例双 handle 运行。五条预期 marker 与固定源码断言匹配，57 件已编译树完整不变。两个独立 context/model 使用同名 TOP scope，导出路由分别选定；交错 checkpoint A=137/B=455，单侧 reset 后 A=7/B=455，销毁 A 后 B 可继续到 469。
- done：源码控制流可计得 110 次 check、220 次 export read、3 次 export write；110/220 是固定 fixture 的静态计数，不是单独插桩的运行仪表。实际运行结论按已审输出、断言路径及固定二进制身份限定。
- done：新增独立安全实际摘要 `development_snapshots/canonical_host93_derived_micro_actual_summary_20261019/ACTUAL_SUMMARY.json`，13,795 B/SHA256 `c60ed76779ba54da2cf1e7b545beffb270e02842b471a536bdf6caaec559d4df`，记录四阶段真实审与精确来源身份。原 14 件 SOURCE 包及其 `PENDING_AT_FREEZE` 全部保持；本追加与单件摘要不作为未来执行授权，不携带本机路径、系统库存、日志、实际生成 C++ 或二进制。
- 边界：原官方生成 native 0/outer 1 的失败、只读静态资格和未初始化风险历史完整保留；旧生成物不因新 tiny 成功而获准 compile/run。新目标构造初始化与一次有限运行不能证明普遍无 UB、任意生命周期模式或全部 DPI 内存路由；本例观察 TOP 导出和经普通端口到达的 leaf count，不是 leaf 私有内存 DPI 资格。
- 边界：四阶段原总窗 30/120/300/30 s、工作上限 10/90/240/10 s 未增；绝对 work-stop 不是可最迟 spawn 后再给整段工作时间。leader 采样不代表 compiler 子树，累计 RUSAGE_CHILDREN maxrss 不当作阶段 RSS。此微例不授 Host ABI、真实 Host 回放或完整 block 数值资格，完整 block 计数保持既有 0/5。
- todo：在独立 SOURCE/身份门与有限预算下继续真实 Host 生成模型、RAM/DPI 接线和数值回放；真实 Host 输入、执行和完整 block PASS 仍需各自证据，不能由本微例自动继承。

### 2026-10-19 00:46 UTC：回退后转单 CI job，先持久化 TEMP_SOURCE

- FAIL/恢复边界：00:38 UTC 实查环境再次回到旧快照，未发布的319提取/13组装/Host配置/生成入口及新工具实际产物缺失；远端 main `18e757084e4812fe2496ba8321438a468e17b646` 与对应 CI success 已重新在线确认。历史 actual PASS 不能代替当前缺失文件。
- TEMP_SOURCE：先提交固定 iDMA artifact `12099239717` 的最小获取脚本与十项人工测试；normal/-O 各10项通过，只核源码/合成HTTP，尚无该下载片真实 CI 网络执行。固定 ZIP 9,926,876B/SHA `a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce`，不解包或执行。
- ongoing：恢复流程转为同一有界 GitHub job，固定官方源→唯一初始化补丁→一次工具构建/微例→同 Host 生成及短 reset/launch。源码检查/阶段hash/资源/终态在job内交接，不依赖已丢失的本地人工审包路径；本批没有触发 workflow。
- 边界：job共享6600秒，Host生成600/540、Host首编译1800/1740、短reset/launch30/10；现场资源前验，超时保失败、不自动重试。本阶段不加载权重/张量，不上传二进制或机器库存，完整block仍0/5。
- 用户长期要求：代码小批及时push，明确PASS范围或临时待验证/FAIL；每小时检查临时清单，每日仅以普通删除提交清理已确定不再需要且可Git恢复的tracked临时数据，保复现source/pin/hash/安全摘要。不删未tracked唯一资产、运行中产物或唯一证据；本批未删除数据。


### 2026-10-19 CI 恢复第二批：319/retained13/监督 SOURCE 临时组件

本批仅持久化新 CI 的三项可重定位源码组件，状态为 TEMP_SOURCE；完整 run、工作流触发及实际 CI 尚未验收。iDMA 提取器只接受固定官方 ZIP 的 319 项精确子集；retained13 按 96 项已发布输入回放生产后像及 front 两补丁；监督薄适配器复用已发布 WNOWAIT 与观测函数。生产执行代码及冷入口保持原字节。仅去除本机 checkout/boot/审查 argv 信息，保留可再生代码、项目来源 pins 和安全冷测摘要。

新 SOURCE 审查：319 6810afd6；retained13 e2bfa648；监督 b98d6462。冷测分别 17+17、7 个入口/信号用例、17+17；没有真实 ZIP 提取、retained13 组装、native 或完整 CI 执行。本批不带源归档、生成 RTL、二进制、原日志或系统库存。下一步仍需完整调用方固定阶段/argv/安全上传 schema 的独立 SOURCE 审。


### 2026-10-19 CI 恢复：4VLT 精确配置 SOURCE 临时组件

本片持久化固定 610 项 public_flat_rd 字段选择、唯一 endpoint 层级边界、21 条来源行号精确 WIDTH 规则和 8 条原 DMA hints，状态 TEMP_SOURCE。来源为已发布项目 pins，610字段的正负微型检查17项在普通、优化及重定位两模式均通过。有限 SOURCE 审05bb9ff2/fe2b71c9闭合；实际配置、Verilator grammar 接受、新 ABI、8 handles 与 Host runtime 尚待本次CI，未从原本机产物继承资格。

所有6件代码/数据/文档按原字节复制；不包括SV、日志、机器库存或binary。isolate_assignments的无作用说明是来源级说明，当前官方grammar原文未恢复，不授实际优化效果。


### 2026-10-19 CI 恢复：工具 v2 与 Host93 发射 v3 SOURCE 临时组件

本片持久化两个可重定位 CI 模块，状态 TEMP_SOURCE，尚无本次 native/下载/实际生成资格。官方工具模块固定 473 源逐 Git blob 核验，先用已发布唯一 m_seqnum 初始化补丁再一次 fresh 构建；现场5version/5tiny、派生工具4阶段微例均由本job新终态和内容hash衔接。十现场probe采用本CI明确30秒总/10秒工作窗口。发射模块固定121项目来源，再按87JAR/20HardFloat→新93→CLASS→CHIRRTL→固定firtool→同SV的顺序复现。

两模块的获取阶段只透传既有平台proxy/CA固定白名单原值，不保存/输出值、不建新代理或凭据、无direct fallback；native仍用clean环境。发射v3在最终保存等异常时重置INCOMPLETE，不让失败报告沿用先前PASS。独审增量fd9d6714/2716b381闭合；工具40+40和7+7运输冷、发射42+42和7+7运输及3+3全mock终态例均通过。所有这些是SOURCE/tiny证据，未执行真实工具或Host。

全部payload原字节；不带源码归档、生成RTL、ELF、原日志、机器库存、权重或张量。整run及Host短launch仍待完整SOURCE审；同一job6600秒总墙不能因各阶段上界之和延长。


### 2026-10-19 单 job Host93 源闭包：完整 SOURCE 已审，首次 actual 待 CI

- 本批以 `b9346e81fd635132a59550a0a50177f4d9624fdb` 为父提交，只加入 composer v3 十二件、Host execution 八件及状态更新；20 件执行/冷测/源 pin/元数据均保冻结原字节，共 128993 字节。工作流由父任务另核后同次发布，首次路径触发才开始实际工作。
- 32 个固定子阶段通过同 job 实际 hash、终态与有界库存传递资格，不依赖丢失的本地审包路径。完整 run 采用 6600 秒共享 job 墙，start+6480 截止内完成工作，末 120 秒留安全验证/上传；逐阶段上限不延长总墙。
- composer v3 作者纯 tiny/mock 为普通/优化各49项，support v2 各21项；Host execution 原组件普通/优化各14项及重定位各14项。源码冷测通过不能替代新 CI 实际资格。
- 最窄路径补丁仅在 `plain_path` 完整路径读取前要求 ASCII `[A-Za-z0-9_/.-]+`，关闭 make 消费 tab、美元符、反引号、分号等路径的整合缺口；原 WNOWAIT 清理与资源/阶段逻辑保持。
- 只准备真实 Host reset 后首次 launch 握手即停，不加载权重、不回放 RAM、不宣称 N0 数值、8 个活句柄或整块数值通过。仅3个严格 schema 安全 JSON允许上传，失败 step/job 不能被摘要覆盖。
- 完整 SOURCE 独审结论为 `SOURCE_GO_SINGLE_BOUNDED_CI_HOST_RESET_LAUNCH_ONLY`，manifest SHA256 `e5e7c995825cb34aceee1f5c67e4d10d43177b286519651a344b9418e82cbc84`，summary SHA256 `6f9aaba2f134dea2833c612b6bb6bd2c5345578407040c64b48eff484e814b58`。对应 run `3895215a…`、support `931c8d8e…`、Host 源 manifest `08ccafe4…` 和父提供的精确工作流。原候选中的 PENDING 是冻结历史，不热改。本批冻结时首次 CI actual 为 PENDING。


### 2026-10-19 首次 Host93 单 CI 实际失败已保全

提交 `7e0ac9fd` 的 run 39185138343 / attempt1 终态 FAIL，payload guard 39185138377 单独成功。原安全3JSON记录主序列63.518112秒，13阶段 EXIT0_CLEANED 后 fresh_make 在47.995942秒 FAILED；Host生成/编译/reset/launch尚未开始。原失败行的退出/CPU为空且cleanup=false来自异常路径默认值，不能推断实际清理失败或OOM。已定位收据投影缺口，原编译根因仍未知。

本批只保存原3安全JSON与解释说明；不提交ZIP、API原文、原日志、系统库存或产物。后继修复失败也保真实退出/信号/timeout/rusage/已确认cleanup，未知为null，并加入固定去敏截断诊断；只做构建诊断资格，保原失败，不自动重试整Host。


## 2026-10-19 CI 构建诊断源码后继（SOURCE 独审通过，actual 未执行）

- 原 Actions 39185138343 保持 FAIL：前 13 个阶段 EXIT0_CLEANED，fresh_make 在 47.995942 秒抛错。原安全摘要未携带私有 native 收据，退出码、信号、timeout、CPU/RSS 和 cleanup 事实未知；初始化 false 不作为 cleanup 失败证据。原失败审 3bdbfc5c / a5729490 已保存，不能倒填根因。
- 本后继仅增加固定失败收据数值投影、有限去敏合并编译日志和显式 build-diagnostic 分支。保原 WNOWAIT / 采样函数、官方 473 源与单行初始化 patch。stop_after_build 默认 false；独立诊断只运行 14 阶段，在 backend 内容身份与原后验后停止，不执行新 backend / 模型微例 / Host。
- 公共三 JSON 严格 v2 schema；未知值为 null。receipt_timed_out 只是原监督分类，最终 reap 负值、原 WNOWAIT 事件和 cleanup kill 分列，不推自然退出原因。编译诊断仅固定 473 公开路径/行列/五类固定文案，merged_log_tail 不称独立 stderr；私有日志、路径、库存和凭据不上传。
- 原 6600 秒 job / 6480 秒工作截止与 make 3600/3570、单核、AS 4 GiB、FSIZE 1 GiB不变；实际 make log 验收 1 MiB，主表允许上限 4 MiB。新 workflow 只由自身路径首次 push 触发，原 Host workflow 不动，不自动重试。
- 作者纯冷测：主 63+63、支持 41+41 与新回归 7+7、工具 41+41、运输 7+7、去敏检查 463+463。独立整链 SOURCE 已闭合：SOURCE_GO_SINGLE_BOUNDED_CI_BUILD_DIAGNOSTIC_ONLY，审 manifest `55cca6e9bc7a56e28b017d152188a8ba983de30dfad2e2b087d0acb3209fbe37` / summary `cc00d4be3e225a45e951c6ff50217731128c3a519da46d6c18d16f1e36843245`；独审新增反例 7+7、支持 41+41、主 63+63 均过，F01/F02闭合。作者测试不代独审。新 actual 尚未执行。只提交再生源码、pin、摘要与计划，不提交任何新生成物。

- 原 v1 HOLD 留存，新 v2 仅禁止准备拒绝后读取旧收据，并使诊断投影受原 phase 截止约束；原异常始终优先。最终内容 17 件源码/metadata/STATUS，加中文计划纯尾与独立新 workflow，共 19 paths；parent 固定 cf0eaa059b029b303d402c983addb0f973b55e0f。首次诊断实际待唯一普通发布触发，结果不预填。


## 2026-10-19 第二次 CI 构建诊断实际 FAIL（39187570266）

- 固定 commit `5f75602a5b5ea8f85c34d8df4b67f256b4a4a7ef`，新诊断 job attempt1 已 failure；仅持久化三原始安全 JSON 与本摘要，不提交 API/joblog、私有 native 日志、生成物或库存。独立实际审待封。
- 前13阶段EXIT0_CLEANED；fresh_make 62.251071s，原waitid code1/status2、最终exit2，receipt_timed_out=false，cleanup_confirmed=true。子进程CPU user60.802876/system1.282175秒，累计子进程RSS峰616720KiB，非阶段专属内存仪表。总73.883024s。
- 合并日志分类输出为空，不能推无错误；当前过滤器只保少数固定分类，未保完整去敏上下文。具体构建根因未知，不推OOM、不改预算。原第一次FAIL保留。
- 下一仅SOURCE：核固定make源闭包与make/g++/bison/perl格式盲区，准备有限完整合并日志尾、路径/secret占位与错误前后上下文。无自动重跑；本次摘要不授任何工具/Host/数值资格。


## 2026-10-19 构建失败完整上下文 SOURCE 后继（独审通过，actual 未执行）

- 原 run 39187570266 保持 FAIL：fresh_make 自然退出2、receipt_timed_out=false、cleanup_confirmed=true；空五类分类输出不能推无错误，编译根因仍未知。原第一次 FAIL 不改写。
- 后继只在失败 fresh_make 读取原私有 stdout/stderr 合并 native.log 的末至多1 MiB；保留最近连续至多80行，逐行去敏后至多512字符，整个诊断 canonical JSON 至多16 KiB。普通 make/g++/Perl/bison 错误及生成源相对名不再依赖五类命中；超额只裁行长或丢最旧完整行。
- 绝对机器路径、URL、常见凭据键值/认证头、长token及PEM私钥块用占位符替换；控制符/非ASCII可见转义。这是固定公开源码与clean native环境的有限诊断，不保证任意秘密文本完全去敏，不开放其他任意工作负载日志。
- context_state 明分 NOT_COLLECTED/AVAILABLE/READ_ERROR/SANITIZER_ERROR，空日志与读/去敏失败不混淆；原失败仍优先。仅stage_exits改v3，summary/source仍v2，仍只有3JSON与总1 MiB安全上传边界。
- 原 WNOWAIT/support/toolchain/官方源/单行patch/clean环境/预算/后验及14阶段build-only停点原字节或原合同保持；不执行backend、模型微例、Host或数值。
- v2受影响normal/-O纯冷测重跑主78+78、旧去敏463+463与新上下文727+727，全exit0；support41+41、回归7+7、工具41+41、运输7+7按未变源码/原日志身份继承v1实测，未重新执行；没有新native、下载、构建或CI执行。SOURCE manifest为6f5b7959c880d60b56638c3472d77cd114ff3292781ad796c499e305f893e402；独立SOURCE审已闭合为SOURCE_GO_SINGLE_BOUNDED_CI_BUILD_CONTEXT_DIAGNOSTIC_ONLY，实际资格不预填。
- 最小发布仅必要源码/pin/测试、安全摘要、STATUS与中文计划；不带原测试logs、私有日志、绝对本机路径或全库存。唯一父发布者待独审封口后另核新一次性workflow；不自动重试原Host，不提升预算，完整block仍0/5。

- 原上下文v1的SOURCE HOLD保留（review manifest 65c775b7eaf50815a905445445b8f19fe634299199dde5f225659c514d0c6f55，summary 491db3c0e57d000ca703096c099a8880c697d02d9c255773ab5778f9d05c852a）。v2仅修F01固定GCC连写路径选项表与F02先识别认证/凭据键值再折叠长token；含MF/MT/MQ/B同类正反例、长键短值和普通文本正控。反例为合成SOURCE输入，不称旧真实日志曾泄露。

- v2独立SOURCE GO身份：review manifest `9c3c5c60198f421581a186f6b7f1012e058d5e65db8336bdfc3552cad137fe8a`；summary `ba9d80bf9f08062c378e4c3253b6ed8090e5d5eb6bb002623b48dd6d2a7f2129`。85静核、独立normal/-O主78各、旧去敏463与上下文727各、原4反例及12正控各通过；未变support/toolchain证据按身份继承。最终13path内容审独立进行，metadata封口未重跑测试，新actual仍NOT_EXECUTED。

### 2026-10-19：FAIL，有限日志已给出 FlexLexer.h 缺失诊断

- ced20f4f 的 build-only run 39191780530 attempt 1 已结束失败；前13阶段成功，fresh_make 自然 exit2，waitid1/2、timeoutfalse、cleanuptrue，54.294193秒。协调入口65.508032秒。
- 安全 context AVAILABLE 实录 V3Lexer_pregen.yy.cpp:369:10 缺 FlexLexer.h（由 V3ParseLex.cpp:30 引入），随后 make Error1/2。原三JSON保存于 development_snapshots/host93_ci_context_failure_39191780530；原两次FAIL不倒填此根因。
- 固定 libfl-dev 选中表已有6893B头（SHA256 ee9859d6b3027ed565f98f42744e438ab31b2cd2e9f797ddf870029ca2021686）；下一最小核暂存目录/include接线并增加真实头编译probe。尚不声明修复成功或backend/Host资格。
- 本批只持久化安全失败证据和说明，不触发新构建；后续修复与有界实际需独立SOURCE门及真实终态。仍保全部复现源码/pin和原FAIL，未清除唯一证据。

## FlexLexer.h 最小恢复 SOURCE 候选

最新保留的 39191780530 仍为 FAIL：flex 2.6.4 已生成 lexer，随后 V3ParseLex.cpp:30 所含生成源在第 369 行找不到 FlexLexer.h；make 自然退出 2，未超时且清理确认。前两次失败保留，不推定同因。

新候选在既有 10 项工具探针后增加两段：只获取固定 libfl-dev 包并经原纯解析函数提取已钉住的单个头；再用 g++ 实际编译小例并核依赖文件确实使用该头。configure 使用同一个显式 -I，生成 Makefile 必须保留该参数，各 build 段前后复核头哈希。两段上限为 120/90 秒（CPU 40）及 30/10 秒，均从原共享 6600 秒扣除，不增加既有资源。

默认完整模式 34 段，头 probe、工具 build 与 tiny 成功才在同 job 继续既有 Host 生成与短 reset-launch；首失败即停。build-only 为 16 段并止于 make。双模式冷测通过：协调 82、工具链 58、单头 26、transport 7、support 41、regression 7、diagnostics 463+727，各 normal/-O 一次。这里只是 SOURCE/合成检验，真实头编译和新 actual 均未执行；独立 SOURCE 审查已 GO，仅限该固定头、同 job 恢复范围。父发布者唯一修改原 Host workflow 注释触发，build-only workflow 保持原字节。

本 SOURCE 冻结 manifest 为 6046 字节 / 8f7a33a6b8a76a62e0455af44b9d34cea79bd98a63cd14d931d1ef252b5a717b；独立审查已 GO，新 actual 仍未执行。

SOURCE 审结论 SOURCE_GO_FIXED_FLEX_HEADER_SAME_JOB_HOST_RECOVERY_ONLY；审查 manifest 1999 字节 / 44303c275d27457eff82fd5f99191553d54aadcb3cd528355d17f22ad0dd8476，SUMMARY 5092 字节 / 87ddb3dfc2e5e39f3eb645639a4e6470c67ee5754e3dc193e3d0d87f23b8d42e。仅为 SOURCE 接受，实际仍为 NOT_EXECUTED，不赋新 actual PASS。

## CPPFLAGS 后验最窄修与安全拒绝码 SOURCE

39193914902 保留为 INCOMPLETE：15 个 native 阶段均退出 0 且清理确认，固定头获取、真实头编译、autoconf/configure 已过；make 未启动，具体私有后验门 UNKNOWN。不得把后续合成反例倒填成本次实际根因。

固定官方 configure.ac 的 CPPFLAGS 尾空格及 Linux 下所选 flex 旁置 include 分支已用原模板小 fixture 证实会被旧逐字比较误拒。最窄修仅按 ASCII 空格/tab 检查 CPPFLAGS += 的已知 token 形态：staged -I 唯一且在前，最多跟随从已验证 flex realpath 推得的一个旁置 -I；额外 flags、目录换序/重复及未批准 MSYSTEM 形态仍拒绝，不新增 make-n 阶段。

summary-v3 增加严格固定 boundary/code，覆盖各 build 前后与 configure 后验合同，保留 native0 事实；不上传任意异常文本或路径，未覆盖旧合同明确 UNREPORTED/UNMAPPED。full34/build-only16、共享6600秒、所有资源/监督/头probe/Host短启动范围均不扩大。

normal/-O 冷测均过：协调90、工具链118、header26、transport7、support41、regression7、diagnostics463+727 每模式。独立 SOURCE 审查已 GO，仅限固定 CPPFLAGS 与安全合同标签；新 actual 未执行，父唯一发布/触发。

本 SOURCE manifest 为6029字节 / d8695b6bc1cd54c724fb3f589e7cc068b0c787c3c1efe490bfee4f0c8a8a48e3；独立审查已 GO，最新实际的具体后验门仍 UNKNOWN，新 actual 未执行。

SOURCE 审结论 SOURCE_GO_FIXED_CPPFLAGS_AND_SAFE_CONTRACT_LABELS_ONLY；审查 manifest 2096字节 / 07d6a2539856f5a1d037d2bec4751d9714b2b44ad51acb1372fe94d326f2c633，SUMMARY 3108字节 / cbdc2da60afb685bcb201e9a123a6a020c68335ac0dbe08a5768f27e4579063c。新 actual 仍 NOT_EXECUTED，不赋真实 build/Host PASS；上一 actual 具体门仍 UNKNOWN。

### 2026-10-19：全部失败子阶段统一有界上下文（SOURCE）

- 实际 39195434991 工具 build/tiny 及 Host class 已成功；CHIRRTL exit 1，14.112065 秒，timeout false、cleanup true。总 609.431408 秒，26 阶段中 25 成功，整体仍 FAIL。
- 原三 JSON 未保留 CHIRRTL 日志，根因 UNKNOWN；不据运行时间、JVM/AS 猜原因，旧证据不改。历史静比未发现命令或资源合同阻点，cwd/Java/locale/权限/新 classes 差异不能定因。
- 既有去敏尾统一用于所有失败 call_phase 子阶段，覆盖 full 34 与 build-only 16 阶段，无逐阶段白名单。失败必须 AVAILABLE / READ_ERROR / SANITIZER_ERROR，无日志为 READ_ERROR；成功仍 NOT_COLLECTED。
- 固定 native.log 末至多 1 MiB，连续末 80 行、每行至多 512 可见字符、规范化诊断整体至多 16 KiB。有限去敏器不变，不保证完美泛化脱敏，不直接采集环境或私有 traceback。
- stage-exits 升 v4；summary v3/source-hashes v2、命令、JVM/AS、资源、监督器及共享 6600 秒不变。旧 v3 实际仍由旧固定 validator 验证。
- normal/-O 各 101/118/26/7/41/7 及去敏 463+727 通过；仅 SOURCE/微例，新 actual NOT_EXECUTED，独审与发布由父统一接续。
- 冻结 SOURCE manifest：7100 B / 564f7f266fe454aa0d78ae2720c733d1170147b09efbbf16a64f8cbf9ea9af92；独立 SOURCE GO（review_ci_all_stage_context_source_20261019T0353），审 manifest 1119 B / 828226c4965ec6032700cca6104b7d5109c829ca94afd9b6f3ef5dc53e54f0ca；审 SUMMARY 3054 B / 517b26c29bf5d0a1ee4a6e8b0d9a87e946fef724d6ddd58413461330f85478e7。新 actual NOT_EXECUTED，原失败根因 UNKNOWN。

### Host93 CHIRRTL 前置与固定源码定位根（SOURCE，实际尚未执行）
- 本轮旧 run 39197065094 保持整体 FAIL；工具链 build/tiny 已真实成功，CHIRRTL 有限尾确证 48 MiB 写盘前上限拒绝，确切长度未知。早前无诊断失败不倒填原因。
- 新显式模式先完成 Java、87 JAR、HardFloat20、93 源组装、class、CHIRRTL 六阶段。只有新 FIR 精确恢复历史 42,417,256 字节/SHA264f8b3a…且原结构断言成功，才同 job 衔接原20工具阶段、2发射阶段、6 Host阶段；复用已得classes/JAR/FIR，不重跑六阶段。不同则保数字与新hash并早停INCOMPLETE。
- 编译期加入唯一固定 project.root，精确指向派生 scala 的父目录，phase cwd不变。固定Chisel字节码及历史注解支持路径机制；57,389,476字节只是静态估算，尚非新实测或恢复保证。
- 原93表、旧emitter和FIR/SV预期身份不改；单项派生emitter保前25行和原结构断言，92算术源原字节。真实UTF8字节/行/module/extmodule/注解数量与字节/scala、src、other分类计数可上传，动态路径不上传。
- 新发射输出上限/FSIZE同步96MiB，AS4GiB、CPU/work60秒、阶段90秒及共享6600秒不增。原默认34阶段及build-only16阶段保持。
- v2 normal与-O各122协调器；继承v1各17组件、42发射微例、3终态、7发射transport及原支持套件均过；v2两次及继承20次全部exit0，158行pin匹配，仅SOURCE/mock，无Java/Scala/native/network。SOURCE审GO，actual为NOT_EXECUTED；无数值/权重资格。
- v2仅补严格schema：完成诊断/AVAILABLE必须绑定六项EXIT0_CLEANED，所有模式第一FAILED只能终末；原正常执行逻辑不动，v1保留。

SOURCE MANIFEST 8d7f3fc6749bc22de9def574836e4eb3247cd834493f4816bbd3956b304a9094；SOURCE审GO，实际NOT_EXECUTED。

SOURCE GO: review_ci_chirrtl_frontload_source_v2_20261019T0429; MANIFEST c440e4eaa8fe194a228b4dbda03b5c7276c59744ce1eb3f65738de143d1218fd; SUMMARY edf619617fe69086c238742f74010daa94cd0bd53d310bfec7e18aab8e08e7c3. Actual remains NOT_EXECUTED.

## 2026-10-19 04:51 UTC：部分 PASS / 整体 FAIL，FIR 与 SV 精确恢复

- 已发布 b0a7a47d 的单次 Actions 39200026785 attempt 1：先六阶段归一化 source-info，实际 FIR 42,417,256 B / 264f8b3a… 恢复固定历史身份；293,837 行、682 module + 17 extmodule，项目/库/其他源标签 249,537 / 4,945 / 0。
- 同 job 按原门继续工具构建、固定双 handle 微例及 SV，SV 76,366,612 B / 2fcc1ba7… 精确恢复。三项工具/发射 scope 为 true，其他 Host C++/reset/数值/权重资格仍 false。
- 31 项 native 成功后，Host C++ 生成自然 exit 2，150.280978 秒、未超时、已确认清理；总 831.028087 秒。去敏尾保留“35 warning(s)”致命退出与部分 UNOPTFLAT，尾被截断，未认定全部告警类别或真实组合环。
- 本小批仅持久化原三份安全 JSON 与范围说明，不改 workflow、不重复触发。下一步只读核告警策略与模块结构，再作有证据的最小修复。原六次失败证据及未知根因边界保留。

### 2026-10-19 Host 生成告警完整诊断候选（实际未执行）
- 原 run39200026785 已恢复历史 FIR/SV 精确身份，工具 build/tiny/freshSV 有限范围通过；第32阶段生成自然 exit2、未超时、cleanuptrue。80行尾仅保4个 UNOPTFLAT 标题及一条35-warning fatal 摘要，不能补全31条或认定行为环。
- 新 host-generation-diagnostic 按原六阶段前置及历史 FIR 门继续到生成，共32阶段，之后停止；不进入 C++ compile/reset-launch。原34/16路径及6600秒共享总墙、各native资源上限、warning-fatal与四VLT原样。
- 对固定 native.log 在既有4MiB上限内完整稳定读取，统计所有warning/error类别，保最多128标题及16条Example公开源身份/行列；64KiB输出预算，显式缺失/截断/未知状态。多个fatal总数不相加，stage完整性不等于process归属。
- 固定endpoint层级参数与wrapper只发hash和有限结构计数，叶wrapper/iDMA聚合只是候选；5条isolate_assignments在5.053无效，不能称隔离生效。本轮不加-Wno-fatal、不改算术/架构。
- 冷测最终136+136、23+23、36+36通过；初始mock注入遗漏与执行测试漏--repo均如实保留。其余未改测试仅继承，不称重测。SOURCE有限独审GO，actual NOT_EXECUTED；父发布后唯一有界诊断job。
- SOURCE GO: review_ci_generation_diagnostics_source_v2_20261019T0513; MANIFEST 1420 bytes / 08dea7a19aa456b4e8fff4c874749143529354e5c4e3941ccc05719f8c50c2dd; SUMMARY 4242 bytes / c25b7abd069253901f6edadc663bbf932c1783384cb0e1c1e32e843bff7b0ce3. Scope: SOURCE_GO_BOUNDED_GENERATION_CENSUS_ONLY_NO_CPP_OR_RUNTIME. Actual NOT_EXECUTED.

## 2026-10-19 05:38 UTC：完整告警类别普查已得，生成仍 FAIL

- 单次 Actions 39204020851 / 59953231 保 warning-fatal，31 native 成功后 Host C++ 生成自然 exit 2（166.252153 秒），总 830.576913 秒；未超时、清理确认，未编译/运行 Host。
- 完整 77,661 B 日志扫描得到 35 个 UNOPTFLAT header（32 固定 Host SV 坐标、3 固定 iDMA 坐标）、2 个无规则 ERROR header、1 个 fatal 摘要，0 未解析/0 记录省略。全 stage 数量匹配不代表进程归属已证明。
- Example 路径 358 条仅保存 16、省略 342，明确 partial；wrapper 摘要 22 输入/21 输出/6 DPI/2 always_comb，依赖结论仍未建立。不得把类别完整升级成全部组合环已排除。
- 本次原三份安全 JSON 与范围说明小批保存，无 workflow 变更、不重复触发。下一步同 hash SV/iDMA 分组核结构，再决定最小修复；原七次失败证据保留。

### 2026-10-19：FIFO 四态与 Host 透明/opaque 配对小诊断 SOURCE

- 原 35 条 UNOPTFLAT 分类和实际 FAIL 保留；本轮只准备小复现，不自动豁免 warningfatal，不改八叶原子握手或数值模型。
- FIFO 只把 valid_o 的原 procedural flush/指针比较独立成组合过程。微例覆盖 Depth 2/3、SameCycleRW 0/1，共 5180 次已编写的稳定组合/手动推进状态比较；尚未真实四态执行，不授完整寄存器宏、reset、时钟或 delta-cycle 等价资格。
- Host 透明/opaque 使用相同八叶 atomic gating，opaque 每叶只有一个全输入/四输出 DPI 调用；这是手写边界模型，无 DPI 实现，不等同真实 22 输入/21 输出 protect-lib wrapper，也不穷尽全部 35 条 SCC。
- 新独立小 job 先固定 Icarus 包取得、FIFO compile/vvp，成功才复用原 20 个工具资格阶段，再生成透明/opaque 两例。总 25 阶段，首个意外失败停；只有最后 opaque 的纯 UNOPTFLAT、精确 warningfatal 数量及 combo/atomic Example 路径可记模型观察，原生非零仍原样记 FAILED。
- 共享时限从 checkout 前 t0 开始，6600 秒总墙内只用到 t0+6480，预留 120 秒安全验证/上传；小例每阶段 30 秒总/10 秒工作，原 make 预算不扩。原 Host 与 build-only 入口不改，无 Scala/FIR/完整 Host 重建。
- 官方 Icarus 12.0-2build2 包 2125764 字节/SHA f19394cee05ad526e0eb3873bc6c17a5828f56df17fbe2db40cb66513a2d4667 已由父唯一只读取得，Zstd/tar/39 选定成员身份已静核。新 host libzstd 适配器仅冷测；本机 UID65534 不满足 UID0 门，已知前拒 probe 不执行、不放宽，实际能力留目标 CI 前置测量。
- runner 27+27、acquisition 40+40 冷测通过；正式整 SOURCE 审已有限 GO，ACTUAL_NOT_EXECUTED。只允许三份有界安全 JSON；完整日志、生成源码和宿主库身份保持私有。
- 原 v1 SOURCE 的三处证据消费关联缺口已隔离修复：FIFO 正观察绑定固定工具身份，clean EXIT0 绑定 waitid/cleanup 成功元组，opaque 正观察绑定 AVAILABLE；执行路径与预算未改。另已审 portable 冷测入口显式接收三个固定数据文件参数，不执行包内程序。
- 独立 SOURCE 审：review_host_micro_job_source_v2_20261019T0621，MANIFEST f1b32efd6d010ab67984d86730dbd339532e4e889b7a9170c4f5f9bd569edd01；SUMMARY c7e8cb9221b88a2114201173b56822a33f2c92138cf837f8baef42ad15f60bb6。实际仍未执行；不授完整 FIFO 或生产 Host 行为资格。

### 2026-10-19：微例取得后父门诊断与固定 libstdc++ 路径修复 SOURCE

- 原 actual39210024872 仅取得子进程自然0/cleanuptrue（1.30257秒），父在 FIFO compile START 前停止，总1.39925秒；原具体后验门未记录，仍 UNKNOWN，原三JSON不改。
- 固定真实包39成员的 receipt/验证/21 ELF闭包静态回放均过，receipt9896字节小于32768上限；decoder身份明确用synthetic字段，不冒充旧CI私有receipt。
- 源码反例确认原路径词法不接受标准libstdc++中的“+”，于open前拒。后继仅给固定系统目录下该库名及有限数字版本形式例外，其余路径、UID、same-fd及ELF门保持。
- 所有父后验补固定安全boundary/code，固定库alias可定位规则；不输出动态路径或异常原文，子进程成功行不改写为失败。
- 新后继仍原25阶段、原6600/6480共享时限和首失败停；不改FIFO算术、原子握手、warningfatal或工具构建资源。v2本轮runner冷测40+40通过，v1的35+35及静读9+9保留继承，旧取得/portable/probe套件仅继承；SOURCE已有限GO；ACTUAL_NOT_EXECUTED，不授完整FIFO/生产Host资格。
- 原 SOURCE v1 HOLD 的 PC01/PC02 仅证据消费关联缺口；v2 保留错误stage-count的INCOMPLETE三JSON，并拒3个已证标签/阶段矛盾。原执行门、成功资格、词法修复及资源不改。
- 独立SOURCE审 review_micro_postflight_source_v2_20261019T0652：MANIFEST eb1f34bbeba3d44986cdc58a913609b269cddb97f4e9e998c7733db68729f4a6，SUMMARY d1ab76eb6fe8f33cda59d5d66b0fd3057b01a1a577286e8b11ecca35b5d57efe。原CI后验门仍UNKNOWN，新实际仍NOT_EXECUTED。

## 2026-10-19：micro 原证据有限复核与观察器格式窄修

- 原唯一 run 39213008977 保持 INCOMPLETE / OPAQUE_OBSERVATION；24 个 native 阶段成功后 opaque 自然 exit 1，未超时且 cleanup=true。原三 JSON 不改。
- FIFO 真实四 case / 5180 比较限抽取组合四态与手动状态步进；20 工具阶段和 transparent 生成成功。Host 配对为 12 输入/4 输出手写 MODEL，不升级为生产 22/21 wrapper 或完整事务等价。
- summary 的 opaque 已接受计数为 0；原 AVAILABLE 且未截断的 60 行安全尾另有 4 条 UNOPTFLAT 与一条 4-warning fatal。固定输入只读复核支持 MODEL 依赖聚合；[PATH] 无法恢复原私有文件归属，不声称 raw observer 已重新通过。
- SOURCE 补片仅 +5 字节，允许既有有限信号名前的固定 top 前缀可选；原文件后缀/坐标、同 warning block、自然退出/cleanup、错误与 fatal 计数门不变。新合成测试不反构造私有路径。
- 原 40+40 冷测通过；新 8+8 通过。可搬迁测试后继只重跑 8+8，40+40 按原字节继承。生产可见性方案只提出具体边界选择及风险，不改 RTL、allReady、算术或单 combo 调用。
- SOURCE 有限审 GO：review_micro_observer_source_20261019T0719，MANIFEST 1753 B / e4705aba0fc221aaedc50755a9165319eb0b48a9bde254698abc8b3da8280a00，SUMMARY 3449 B / 0ebfdfc599d55a85a0374d7e7cdc0fd0f62369ec633c250501e226eb493970b9；verdict SOURCE_GO_FINITE_OPTIONAL_TOP_PREFIX_OBSERVER_ONLY。独立复核 40+40、8+8。本批不改 workflow、不触发重编或新 job，生产方案仍只读提案。

### 2026-10-19：cluster 边界与 FIFO 单项派生，生成诊断候选

- 当前父提交 d03e8fec；前次 39213008977 原 FAIL 与安全观察保留。FIFO 真实 4/5180 仅涵盖抽取组合逻辑及手动状态；Host 透明/opaque 仍是 MODEL 观察。
- 固定源级逐项核 40 个 cluster 当前输入→两输出对、4096 payload 读路径及同步写：输出为寄存 FIFO 头，无当前输入/写穿/pop 旁路。真实 out_ready→step_ready 与全叶 allReady 原子握手保持。透明范围是握手/准入；seed bank、结果/flags 读指针仍留 cluster。
- 唯一 generation-diagnostic 变体采用已审 valid_o 拆块和既有 cluster hier_block。319 文件总 3072325 B，仅 FIFO +125 B；原 927 表不热改。两既有 WIDTHEXPAND 原语句 81/100→88/107 精确迁移，零新增豁免。
- 官方固定层级源码支持同参数共享一个 specialization/library 规则；每实例 model/seqnum 分开，VerilatedContext 并非各建；clock 任意分类变化触发 seq，单个静态 combo 调用点不能推出每周期动态次数。
- 32 阶段及共享 6600 秒不变，生成仍 600/540 秒、AS 6 GiB；生成后停，不运行 Host C++ compile/reset。报告从产物计 make 规则/handle，缺失 MISSING、未知语法 UNRECOGNIZED，不能把期望 256 倒填实际。
- v3 仅重跑 census 57+57 与 coordinator 136+136；extractor 22+22、configuration 21+21、execution 27+27 继承原样 v1。四类 census 范围/候选漂移/计数缺口保留 v1 HOLD，v2 窄修后两项同类边界另存 HOLD，v3 只认 root 直接成员，嵌套类型/函数声明降未知；零 always_comb 保 census 并降未知。均源码/mock，无 native。SOURCE 独审已闭，actual NOT_EXECUTED。

- SOURCE 独审已 GO：review_cluster_fifo_generation_v3_source_20261019T0759，MANIFEST ae4cb32c220aa1b8e20dd2a83fa68a43048b8aa20176b93aa4e2e4016bc32f8e，SUMMARY 791bb998b85747a22dd018c37881d8f47af600c98851ed5e921cfe0702c692c4；actual 仍 NOT_EXECUTED，生成后仍停。

### 2026-10-19：cluster 生成诊断 39220292509 原 FAIL，剩余 iDMA 单告警

- 提交 0a1c06be 的唯一 run 39220292509/attempt1，32 阶段31成功，生成自然 exit2/未超时/cleanuptrue，97.573698秒；总574.048876秒。FIR历史身份、工具build/tiny与freshSV通过，Host生成/编译/reset/数值资格仍false。
- 完整4001B日志有1个UNOPTFLAT及全部9个Example，0未解析/省略；前次35降1，本次定位idma_axi_read:87。cluster实际wrapper18入2出、6DPI、单combo点、两always_comb；单匹配archive规则不代表库已编译，specialization与256handles仍未知。
- root_header CONTRACT_ERROR且identity=null，首次固定读取未返回、parser未进入；缺文件本应MISSING，不能倒填具体读取门。后继仅需固定安全读取码/观察size，不盲扩cap或parser。
- 固定源支持remaining ready_o过程聚合候选：保真实SameCycleRW ready_i依赖，将ready_o原flush分支独立；iDMA原子gating和allReady不动。先前4/5180不能授新拆块资格，下一需相同四态矩阵与背压小测重新实际验证。原三JSON/FAIL保留，actual独审已接受有限失败证据。
- actual独审 review_cluster_generation_actual_39220292509_20261019T0821：MANIFEST eb09e9bd53bba6456b898b693d6f753b23fd2a1599d6668e13c6335a252457b2，SUMMARY 924da874fe0c25f3f3af51d2ab8b534ed6d6e33f3b913d09e9045eb4b72eadb8；只接受原失败证据。

### 2026-10-19：FIFO ready 双拆块与同 job 四态前门（TEMP_SOURCE）

- 原39220292509仍为INCOMPLETE：完整4001B日志剩1条UNOPTFLAT，9条Example齐全；旧root_header原因与256实例数未知，不倒填。
- 固定NoCompute源锥独核支持过程聚合反边候选：ready_o方程不依valid_i，原大块却同时读valid_i并写ready_o。保SameCycleRW真实ready_i依赖及原flush procedural语义，不能推广为全设计无环。
- 本后继仅把ready_o两条原赋值移入独立组合过程，保原valid_o拆块、状态更新、iDMA原子gating与算术。4411→4536→4662单成员身份明确，319合3072451B；原两WIDTHEXPAND仅81→98、100→114精确同句迁移，零新增豁免。
- generation-diagnostic同job先3个Icarus/FIFO阶段；真实4case/5180必须通过，再走原32阶段，保共享6600秒与原限额、首失败停。既有reference/cases不改，不重复Host模型或工具阶段；全链34/build16原行为保留。
- 四态资格限抽取组合方程与手动状态矩阵/背压轨迹，不授FF/reset/delta周期或生产数值等价；旧5180不能替代新派生实际。
- root_header仅加固定读失败码与实际字节长；首4MiB读仅SIZE_LIMIT且size≤16MiB才条件重读，稳定性合同/解析器保持，超过16MiB仍未知。
- 当前仅SOURCE/mock；新actual NOT_EXECUTED，独立总SOURCE审GO (review_fifo_ready_whole_source_20261019T0847; manifest b8980bdc7114e4848d11092757aac00d04b5d57641cc55b8832e3578e3a42e69; summary b6a1b784b5301dc410478ecc07077e2c3432452047f0b4f451873d096571d61e)。生成仍warning-fatal，禁止Host C++compile/run、权重与长数值；仅三安全JSON可上传。

### 2026-10-19：新FIFO双拆块+cluster生成有限实际通过（39226255480）

- 原attempt1 Actions success，源码4f915090；三JSON原字节保留于development_snapshots/host93_fifo_ready_generation_success_39226255480。总839.870341秒，35native全部自然0/cleanuptrue/无timeout。
- 新派生真实Icarus4cases/5180通过；资格限抽取组合/手动状态与背压轨迹，不授FF/reset/delta或生产数值等价。原工具build/tiny、历史FIR/SV精确身份均通过。
- 生成127.233662秒自然0，完整1874B日志0warning/0error/0unparsed、零遗漏，fatal策略未关闭。单cluster wrapper18入2出、1静态combo点、1匹配archive规则；不当成已编译库或动态次数证据。
- root header5296945B首次SIZE_LIMIT、16MiB条件重读OK，后验仍UNRECOGNIZED_SYNTAX；256handles未知/null，expected_structure=false，不推定未知语法原因。
- 原summary保持DIAGNOSTIC_ONLY_REQUIRES_ACTIONS_EXIT0；Host C++compile/reset-launch、数值与权重scope仍false。下一compile+短刺激须独立SOURCE续跑接口审核，本小批不改workflow、不触发。
- 独立actual审身份GO（review_fifo_ready_generation_actual_39226255480_20261019T0913；MANIFEST 5391de4dac6d078be67847c4aa341542733784256b329b6815dce1c7c1b7cbb0；SUMMARY 43c8f1b3d2d1a09f6f07c988e9f5052286f99d145ddb4db96e234f886945c772；仅四态抽取组合与Host生成有限资格）；原失败历史均保留，不用本轮成功倒填此前失败原因。

### 2026-10-19：cluster同job编译与原短reset/launch后继（TEMP_SOURCE）

- 已持久化39226255480有限成功；原35阶段/4cases5180/零warning和root header语法未知/256null不改写为完整Host运行资格。
- 新显式mode host-cluster-reset-launch为37阶段：复用同job现有FIFO前门、精确FIR门、工具/Host生成，再接原1800/1740编译与30/10短reset-launch，保共享6600秒及所有原资源上限。
- 旧endpoint参数/8handles门不适用于cluster。新窄门绑定实际单cluster args、wrapper/top链接、m_seqnum0构造、83顶层口及生成树身份；编译后核新child/top archive和ELF，前后输入/生成文件/ELF不漂移。
- 既有census须完整零warning/error、有限18入2出/6DPI/1combo/2comb与1匹配library规则才许编译。root header解析器不扩，未知256不伪填；此资格限真实链接和短刺激，不称全部实例/DPI数值等价。
- 原short_launch.cpp/launch payload字节不变：reset高/低各4个高边沿，最多16候选边沿内首个真实launch握手即返回，此后零eval/无显式final；AXI输入仍全0，不供RAM响应、权重、完整协议或长数值。
- 当前SOURCE/mock；新actual NOT_EXECUTED，独立SOURCE审已GO。原35/34/16模式保持；首失败停、warning-fatal与三JSON安全上传保持。
- 审前v1误读根目录旧同名无参数RTL，未发布/未执行；v2改由固定retained13真实投影与Host参数传递闭合。unsigned bit参数ENABLE_ACCUMULATOR_SEED确为1，固定官方序列给出1'h1及SHA512特化名前缀，逐args/wrapper/构造/archive绑定；不由旧安全摘要UNKNOWN推无-G，也不宽松接受任意后缀。
- v2冷测仅本次受影响协调器153+153与execution44+44；FIFO17+17、extract24+24、config22+22、census68+68及其它未变测试继承，不冒称重跑。
- SOURCE独审身份：review_cluster_reset_launch_source_20261019T0932，MANIFEST d5f9c6e56c727a4f15595eb116cfe6f2a2a63dd8d53f413d60de3ece9592ecdd，SUMMARY d0550433add06abb32f26a09b176f94c5f9b54d56b71d182c282fb394ce4f686；有限37阶段编译/原短reset-launch源码获审，actual仍NOT_EXECUTED，未知256与无RAM/数值范围保持。

### 2026-10-19：首次 cluster Host 编译与原短 reset/launch 有限实际通过（39232100796）

- attempt1 Actions success，源码29e0c301；原三JSON保存于development_snapshots/host93_cluster_reset_launch_success_39232100796。总870.427722秒，37native全自然0/cleanuptrue/无timeout；生成123.743956秒、compile/link56.433910秒、reset-launch0.055328秒。
- 同job真实FIFO抽取组合4cases/5180再次通过，工具build/tiny及历史FIR/SV精确身份通过。完整1872B生成日志0warning/0error/0unparsed、零遗漏，原warning-fatal保留。
- 已pin新cluster门核seed=1特化、wrapper/构造/库/83顶层口与新ELF稳定链；安全摘要报告ELF13323224B/9bda15e2efa466a55632d34bd1aeba21d223102a88e47618fe975247fad56aba。私有生成物未上传，不称独立重读或256实例隔离证明。
- 原短刺激字节不变，reset高/低各4个高边沿，最多16候选边沿中的首次launch握手后零eval/无显式final。成功路径检查三marker，但成功raw log未上传，当前只据固定源码/原收据及scope作有限结论，不冒称复读marker或具体握手边沿。
- cpp_generated/cpp_compiled/reset_launch首次在本路线实际为true；AXI输入仍全0，无RAM响应/权重/N0数值/fullblock，相关未授范围不因Actions成功扩大。FIFO5180也不授FF/reset/delta等价。
- root header5296945B有界读取OK但语法仍UNRECOGNIZED，256handles仍null/UNKNOWN；不扩parser、不伪填。独立actual审已接受有限范围：review_cluster_reset_actual_39232100796_20261019T1006；MANIFEST 1066 B / fa51d430f3851a556b7c6f2472e1ddb3f6e475c43abeabcdde86958801f5b22f；SUMMARY 11813 B / 120ffd07a662deb267be143b1c890c87d787637e2ac8d50da91c79a8963edbb3；verdict PASS_ACTUAL_CLUSTER_HOST_COMPILE_AND_BOUNDED_RESET_LAUNCH_ONLY。
- 本次仅安全五路径持久化，不改workflow、不触发新的 Host/native 作业；下一首数值阶段先只读核已有冻结输入/参考/驱动和最小缺口，尚未运行。

## 2026-10-19 首个 M128 N0 前门有限源码持久化
- 本批 TEMP_SOURCE / NOT_EXECUTED：固定官方 Qwen2RMSNorm 单次参考恢复与 raw13→provider14 当前收据来源绑定；无 workflow 修改，不触发新的 Host/native 作业。
- 原13 raw /14 provider 全部负载身份不变；收据只绑定当前固定获取计划，期望4335 B/0b319b9d…属于 SOURCE 推导，不伪造历史实际。
- 参考保持196608值、原双SHA、原五native SHA、AVX512与4intra/1interop，不自动换AVX2或放宽hash。
- 后续已批前门1440秒：wheel300/raw900/provider120/reference120；setup与所有阶段同扣6600总墙，最后120秒安全落证。参考AS8GiB/CPU90，RSS1.5GiB仅采样软限，安装树边界是观察/验收上限。
- N0仅计划8M探索帽、wall3600/CPU3540/Host单核AS6GiB，受共享余量；2428928计算下界不是完工上界，预算耗尽INCOMPLETE。单RTL/单RAM的真实B→ACK0→全值读回桥尚未完成，不在本批授予数值资格。
- 当前cluster身份不能继承旧8endpoint门；root256仍UNKNOWN。无权重/张量/二进制/完整日志上传，无后续block或fullblock资格。
- 参考 SOURCE 审 review_frozen_n0_reference_source_20261019T1036：MANIFEST 1227 B / 6ea5150332941dbacc9ec5304887c2ac2e0ffa3e4706ac5f1202f95f39a0b4fd；SUMMARY 4492 B / 91e8dbf66951f56916fac12b48ea9bf9f9e6c77498b776155620e294e12797ad。收据 SOURCE 审 review_n0_receipt_binding_independent_20261019T1036：MANIFEST 1013 B / 02e7a4e205b8ae11eecef952fd7bb1c37a67bb70eb4174befe7a0fb183d15933；SUMMARY 4598 B / b27b3431547e14ae991a7b03c492fb00032553b05c1483c9541bd3114525e23a。独立参考24+24、收据14+14通过；均仅SOURCE，实际NOT_EXECUTED。

## 2026-10-19 首个 M128 N0 有界同作业 SOURCE 后继（SOURCE已审，尚未实际）
- 新 host-cluster-first-n0 43阶段复用当前cluster/seed1参数/同作业archive与ELF，固定16输入和原参考双SHA；root header语法与256 handles仍UNKNOWN，不沿旧八endpoint门。
- 单RTL单RAM，完整12288次B退休→ACK0→196608值读回，无进一步eval。原比较五函数、FP32→FP64、max_abs≤.03125/mean_abs≤.005保持；容差PASS与bit/hash exact分列，不授wholeblock。
- 五前门1440秒，参考AS8G/4intra1interop/CPU90/wall120；N0窗口3600内预留原比较30秒，模拟单核AS6G。共同6600从checkout/setup前计，末120安全保留；8M探索帽、2428928归约下界及5571072未证余量明确。
- 新数据/runtime/numeric日志只出固定安全码与有限计数/aggregate指标。周期/资源超限INCOMPLETE；仅完整原容差比较false为数值FAIL。原fatal/监督/旧mode与另外两workflow保持。
- 主178+178与adapter API47+47均纯mock，fresh82来源投影source-only exit0；组件独审冷测分别继承，未实际参考/模型/权重/数值。总SOURCE已有限通过，父唯一发布/启动；此处不预填PASS。

v1 整体有限HOLD仅三项；v2已隔离修复比较失败后参考复读标签关联、比较收据首次读取/JSON固定错误映射、仅新mode共同截止固定码。原native异常优先、数值/资源/阶段不变；178+178和47+47为本v2重跑，组件结果继承。v1审MANIFEST2da2084592c139b66f6c3f0c69aaf06b9053a3b94b1fc82b571513a7a7365669，SUMMARY40a91f106e92eba56be2fe6bddd00e7a222b99e82dd30ca9fa914930961269da；v2总SOURCE已有限通过，实际仍NOT_EXECUTED。

总SOURCE正式审：review_first_n0_whole_delta_20261019T1117，MANIFEST 2517B / 313e60aaf65d0a7d5d4c0526fca8291e9b2aa41c08ef1fef51411ba7a17712de；SUMMARY 5816B / 5662b24df8aa688ef0db25206eb51e9cc11aeeb45036400d36a370b0ef4f78d3，结论SOURCE_GO_FIRST_M128_N0_SAME_JOB_43_STAGE_ONLY。只授有限SOURCE，实际与数值结果尚未执行。

### 2026-10-19：首个 M128 N0 在 RAW_OUTPUT 前门终止（39246774912，原失败）

- ccdd46b8fcac78834dd462f00a821c9430b3f7d2 的 run 39246774912 / job 118040497230 / attempt 1 已终态 failure；原 summary 为 INCOMPLETE / INPUT_OR_CONTRACT，总 8.293286 秒。仅 wheel 0/1.875846 秒、runtime install 0/5.526463 秒、raw 1/0.101443 秒三阶段，均自然退出、无 timeout、cleanup_confirmed=true。
- 安全 marker N0_ACQUISITION_FAILED:RAW_OUTPUT:RAW_RULE_014 精确映射原 acquire_raw.py:299 的历史 work 路径分量拒绝；具体展开 CI 路径未出现在本批三份安全 JSON 中，本批不复制 Actions 日志中的机器路径。prepare_output 拒绝发生于 collect_fixed 前，因此未到张量获取，provider/冻结参考/FIFO/toolchain/Host/N0 数值阶段均未执行。
- 原 summary.contract_failure=UNREPORTED/UNMAPPED_CONTRACT 与 raw 阶段 NATIVE_SUPERVISION/CHILD_EXIT_NONZERO 原样保留，不以源码归因改写。只有 runtime_ready=true；inputs/reference 和全部 scope 资格仍 false，capture/comparison NOT_COLLECTED；保留的 COLLECTING 状态不代表作业仍运行。runtime 安装通过不授冻结参考数值资格。
- 原三份 JSON 保存目标 development_snapshots/host93_first_n0_raw_output_failure_39246774912；82 个固定 project_sources 的 size/SHA256 对应本提交。失败摘要部分固定为四件安全证据与本计划追加，actual 独立审核已接受有限失败证据（review_first_n0_actual_39246774912_20261019T1150；MANIFEST.json 1852 B / cc711667ee6074321c4a4e4e27b5054d5abb9fa3fe48eb032800b25c78cb6e5c；SUMMARY.json 6930 B / 88b3b19aa816f08e83116b644cd916b476efbe2ec0ff009cd358a91e8b8e5725；ACCEPT_ACTUAL_FIRST_N0_RAW_OUTPUT_PREFLIGHT_FAILURE_ONLY）；此失败摘要仅补审核元数据，不改原失败，也不包含 workflow/源码或重跑；合批另带下述独立已审的输出目录修复，不发布私有日志/权重/张量。

## 2026-10-19 首 N0 raw 输出目录最窄恢复（TEMP_SOURCE，SOURCE 已审）
- 原失败 RAW_OUTPUT:RAW_RULE_014 证明历史 work 分量门命中；展开的 runner 路径未出现在本批三份安全 JSON 中，本批不复制 Actions 日志中的路径。保留原 raw 安全门，仅将 Host workflow 私有输出根固定为 /tmp/host93-first-n0-${run_id}-${run_attempt}，核 run_id 数字/attempt1/根精确绑定，actual、safe verifier、三文件上传统一同根。
- 真实固定入口 → 全部原来源检查 → 原 prepare_output 的 11+11 双模式网络前测试通过；严格截停 strict_opener、禁止 collect_fixed，无张量下载或 native 执行。新增 portable 测试显式三绝对参数，同 buffer size/SHA 前验；原 Python 生产代码、43 阶段、共享 6600 秒与原预算/数值门不变。
- SOURCE 有限审核已通过：review_n0_raw_output_workflow_source_20261019T1153，MANIFEST.json 2609 B / 8ab1f343ea7c2eb08215b0d989ac1e61ad90bd5da41b599dc93f688b90957a85；SUMMARY.json 2688 B / b030cc9b8d9f1bb781f1fb7af9a442ddabf76a5a52e7eab385418f886ae8deb1；SOURCE_GO_FIRST_N0_WORKFLOW_FIXED_TMP_ROOT_ONLY；新实际 NOT_EXECUTED，未授 N0 数值或全块资格。下一唯一作业由已审 workflow 触发，首失败停；冷测试不是张量获取或参考运行资格。

### 2026-10-19：首个 M128 N0 在 DISPATCH 前门终止（39248526073，actual 已审）

- 原 run 39248526073 / job 118046310718 / attempt 1，执行 head fd16bcf9dbcd9ea6ca54c35754d6aa51d8fba327，已终态 failure；原 summary 为 INCOMPLETE / INPUT_OR_CONTRACT，总 21.214023 秒。五阶段 wheel 0/2.206252 秒、runtime install 0/6.090402 秒、raw 0/7.458911 秒、inputs prepare 0/1.064079 秒、reference 1/3.626513 秒，均自然退出、无 timeout、cleanup_confirmed=true。
- 唯一安全 marker NOT_COMPLETED:DISPATCH 定位到已绑定 n0_reference.py:190 的 capability equality 门；PINS 固定要求 AVX512，实际 capability 字符串未出现在这三份安全 JSON 中，本批不猜测具体值。依源码控制流，先前固定来源/官方类、raw2、ci31214 Python profile/解释器、五份 native library 和 runtime source 身份、4/4/1 环境门与 NumPy/PyTorch 版本/torch commit 门已通过。
- torch.set_num_threads(4)、torch.set_num_interop_threads(1)、deterministic 设置、build-SHA equality、模块路径检查、官方 forward 与后续 postflight 都在失败门之后，尚未到达。runtime_ready=true 不授冻结参考完整运行时或数值资格。inputs_ready=true 经固定16 receipt 检查仅代表输入已准备，不表示加载到 RTL；reference_ready=false，capture/comparison NOT_COLLECTED，全部 Host/数值 scope=false；COLLECTING 是遗留状态，不代表作业仍运行。
- 原 summary.contract_failure=UNREPORTED/UNMAPPED_CONTRACT 与 reference 阶段 NATIVE_SUPERVISION/CHILD_EXIT_NONZERO 原样保留，不用源码解释覆盖原报告。原三份 JSON 和中文说明目标为 development_snapshots/host93_first_n0_dispatch_failure_39248526073；82 个 project_sources 的 size/SHA256 与父提交 c4ecd4a4b77e85137eba5746f0c77f72b9e0e452 相符。Actual 独立审核已接受有限失败证据（review_first_n0_actual_39248526073_20261019T1203；MANIFEST.json 1852 B / 8f297a1e9891d999f2f01a80ad002701acde345638ab09a9538293588f0f49b2；SUMMARY.json 9361 B / 059b5eda5f5837ae6ae4bc060cc018b60d2e436b84787202a2aa2bd5fa82afeb；ACCEPT_ACTUAL_FIRST_N0_REFERENCE_DISPATCH_PREFLIGHT_FAILURE_ONLY）；本 v2 只补审核元数据，形成安全失败摘要和本次纯尾追加，不含 workflow/源码、权重/张量/二进制/完整日志/系统清单，不授 Host、N0 数值或全块资格，也不重跑。


### 2026-10-19 独立自然 dispatch N0 诊断源码（TEMP_SOURCE）
- 原 39248526073 的固定 reference 能力门拒绝已另行保存；该原 FAIL、未导出的实际能力枚举和主基线均不改写。此批仅新增独立四阶段入口与独立 self-path workflow，原 43-stage Host workflow 不变。
- 固定流程：11 wheels 获取与离线安装共 300 秒子窗口；只取原两项 Range 共 789,504 字节、180 秒；自然 capability 候选 120 秒。共享 600 秒 work 从 checkout/setup 前开始，另留 120 秒安全落证；所有子阶段按剩余时间裁剪。
- 原 Python/native/source/raw2 哈希、Torch/NumPy 版本、4/1 线程、确定性与官方类一次 forward 保留。只允许自然 AVX2/AVX512 对应原已冻结 build digest；DEFAULT/OTHER 在 forward 前停止，禁止强设 ISA。
- 原 BF16 与 FP32LE 两个 SHA 强比；即使两者相等，也仅记录独立候选事实，reference_accepted、baseline_adopted、DUT/fullblock 全为 false。不同哈希保留自然 exit 1；资源/准入/后验失败为 INCOMPLETE，不把它当数字不匹配。
- 只上传三份严格安全 JSON：固定能力枚举、到达/通过门、形状/双 SHA 布尔、有限原生终态、soft sampled leader RSS。失败日志仅取至多四条固定状态标识；无张量、私有全文日志、系统清单或任意路径。
- coordinator 19+19、搬迁 19+19；raw2 53+53；candidate 18+18、搬迁 18+18，均为纯源码/stdlib/mock。没有实际获取、数值 import/forward 或 DUT 执行。原 D01/D02 HOLD 保留，新后继只补可信测试入口及成对观察字段原子提交/原失败码优先。
- SOURCE 独审身份：review_n0_dispatch_coordinator_20261019T1221: MANIFEST.json 1189 bytes / 6362d7dd7060e9a8b9fc5216ee4a9355569929f10654b63426b9c818bbc2f339; SUMMARY.json 5432 bytes / 602e9cbb587b9ac52c4d9a564c3d31b88181a7d9ecc2db53c431723ea3b3ce84; verdict SOURCE_GO_INDEPENDENT_N0_DISPATCH_FOUR_STAGE_DIAGNOSTIC_ONLY；本批实际状态 NOT_EXECUTED。后续唯一实际由父按已授权四阶段执行，独立结果须审后报告，不能自动接回 DUT。


### 2026-10-19 独立自然 dispatch N0 候选实测成功（未采纳基线）
- 原 run 39252523415 / attempt 1 / head 07bb63edae88a95ec4aadd28d2ebf6ee0e81768c 为 success；协调器 18.262813 秒，四阶段均自然 exit 0、未超时、cleanup true。仅保三份安全 JSON 与说明，不重新运行。
- 本次自然 expected/observed capability 均 AVX512，11 项 source/runtime/raw2/线程/build/forward/postflight 门全通过。原两项 Range 合计 789,504 字节，一次原官方类 forward 的 `[1,128,1536]` / 196,608 值形状和有限性门通过；原 BF16 与 FP32LE 双 SHA exact 均 true，未放宽原哈希。
- 原摘要 CANDIDATE_EXACT_MATCH_ONLY / AVAILABLE；reference_accepted、baseline_adopted、DUT/RTL/fullblock 均 false。它仅是独立参考候选事实，不授 Host N0 容差数值 PASS、AXI/单 RAM 退休、RTL 读回或 wholeblock 资格。
- 采样 leader RSS 308,408 KiB 是有限软观测，不是硬限或整树峰值；私有张量/receipt/成功日志未上传，本地未对其重新读回哈希。前次 39248526073 实际 capability 枚举仍未知，不能用本次 AVX512 倒填，亦不保证下次硬件能力。
- 实际独审身份：review_n0_dispatch_actual_39252523415_20261019T1236；MANIFEST.json 1032 B / f4adc0bb88800054fbf9aac77c9d84c8cd87009034aadb4e0009d2c76882bc38；SUMMARY.json 7225 B / 889efb81b48c3b7a50fbec0495511f912bac6dedb9b426324bc127f6a6e62ae6；ACCEPT_ACTUAL_INDEPENDENT_N0_NATURAL_AVX512_DUAL_SHA_EXACT_CANDIDATE_ONLY。本次安全五路径不改 workflow/源码、不触发新的 Host/native 作业；文档 push 仍可能运行 guard。计划发布必须验证当前全文前缀，再完整替换一次，严禁把完整文档再次 append。

## 2026-10-19 原首 N0 严格参考失败的有限能力观察补片（TEMP_SOURCE）

- 已保存独立候选 39252523415 的自然 AVX512 与原双 SHA 一致事实；该候选不接入 DUT，不替代原参考 receipt，前次能力未知不倒填。
- 本次仅在原 43 阶段第 5 个 n0_reference 原 native 失败处理器读取同一私有 RECEIPT.json，最多 65536 字节；公开 expected=AVX512 与 DEFAULT/AVX2/AVX512/OTHER/UNKNOWN 固定枚举及 NOT_COLLECTED/AVAILABLE/READ_ERROR/SANITIZER_ERROR 状态，不公开任意文本或机器清单。
- 消费端绑定前四阶段 clean 成功、运行库/输入准备完成及第 5 阶段 FAILED；能力观察不授 reference_ready 或数值资格。收集错误保留原异常/退出/清理，启动前 deadline 拒绝不误记已收集。
- 原 reference/PINS、官方算术、自然能力准入、4/1 线程、双 SHA、43 阶段、6600 总墙与各段预算均原样；独立候选 receipt 不参与。本次实际 NOT_EXECUTED；未来仅获准一次原流程，再次 DISPATCH 拒绝即停并报告资源缺口，不自动重抽。
- 冷测主协调器 187+187、适配器 58+58 真实通过；82 来源 source-only 通过。原 recover 独立冷片以全 mock 验原唯一门，AVX512 在线程前哨点停止，不冒实际调度或 forward。SOURCE 审核 SOURCE_GO_ORIGINAL_N0_REFERENCE_FAILED_CAPABILITY_PROJECTION_ONLY; review_n0_reference_capability_projection_source_20261019T1249, MANIFEST.json 1435 B / 842a968e480266e931b6e8b6dcd78502214adea4b191303f58b6bdaed26de6ef; SUMMARY.json 3698 B / e847d25a491b6e0a59d83e1947639fafc3987810526ee66b5c835c5deada954f。
- 本计划提供完整文档替换，并校验既有前缀及纯追加尾；不得把完整文档再次 append。原历史证据保持其原源码身份。

## 2026-10-19 原首 N0 严格前门实际 AVX2 拒绝并停止（39255764538）

- 原 run 39255764538 / job 118070526536 / attempt1 / head6322568f426af70115a313d5f5bf708df4c648ea 已 completed/failure；仅保存原三安全 JSON 与准确 README。Actual 独审 ACCEPT_ACTUAL_FIRST_N0_ORIGINAL_AVX512_GATE_AVX2_OBSERVED_FAILURE_ONLY；review_first_n0_actual_39255764538_20261019T1259，MANIFEST.json 1016 B / 0cb4e1ae4c14938cfc572d246e8bd80af54e6d763cc8fa5a32dfe808a18dc042；SUMMARY.json 7125 B / e04273ae5fff00333a07786543cd058a2ef542a4c5b0391bc377004c542d29f4。
- 前四阶段自然0且 clean；n0_reference 自然1、3.628454秒，无 timeout、cleanuptrue。19.598964秒是协调器用时，不含 checkout/setup/upload。
- 本次固定安全观察 AVAILABLE：expected=AVX512、observed=AVX2，尾为 NOT_COMPLETED:DISPATCH；严格原门因此拒绝。原顶层 UNREPORTED/UNMAPPED_CONTRACT 保持，私有 receipt 未上传或独立复读。
- 原参考线程 set4/1、build equality、官方类编译/forward、双 SHA 输出验收未到达；工具、Host、DUT、捕获和数值比较均未到，全部 scopefalse。canonical16准备不代表权重加载到RTL，本次不是 N0 数值 FAIL。
- 按授权边界停止，不自动重抽、不重跑43阶段、不降低原profile/双SHA；后续缺口为满足原冻结AVX512 profile的可用执行资源。39252523415独立候选自然AVX512/双SHA事实保留且未采纳，较旧未知ISA仍未知。
- 本批仅安全五路径，无workflow或执行源码变化，不触发新的Host/native作业；普通文档push仍可触发guard。计划按验证前缀的完整文档替换，禁止append整份全文。

## 2026-10-19 本地 historical 原参考资格薄探针 TEMP_SOURCE（实际未执行）
- 原 39255764538 的自然 AVX2/原 AVX512 门失败已保留；没有自动重抽、没有把此前候选采纳为基线。当前新增仅隔离的本地四阶段源码，原 43 阶段及所有 workflow 不变。
- 精确复用原 PINS 中 historical CPython：30,894,944 B / fa67443527ed9647f760d807e2a38f26340757123e643c4639cf273ed15d5ea7，版本前缀 [3,12]；与 CI ci31214 分列。11 个官方 wheel 原 URL/size/SHA、获取/安装/树观察函数不变，仅四处解释器绑定与说明句派生。
- 四阶段为固定 wheels、离线安装、既存 raw2 只读身份、原 n0_reference.py --python-profile historical。两原资产总 789,504 B，不写原目录、不复制进 Git；仅产生新的私有同资产身份收据，明确不冒充先前 CI same-job 下载收据。
- 原官方类、一次 forward、五库/原运行时来源、自然 AVX512/4-1 线程/构建、BF16 与 FP32LE 双 SHA 全保；仅四 native 成功清理、原 PASS 收据、RSS 观察、父重读 FP32LE 及源/raw2 后验共同通过才给 local_reference_qualified。baseline_adopted/DUT/fullblock 始终 false，成功 BF16 只有原 worker 报告 hash、不冒称父重读。
- 共享 720 秒外层从任何源检查/包动作前开始，work 600 秒，留 120 秒安全落证。wheel/install 共 300 秒，raw 只读 30/10，原 reference 120/90 CPU/8 GiB AS；参考采样 RSS 1.5 GiB 是观察验收且仅 leader。所有上限扣同一剩余预算，不自动重试。
- 本轮 31+31 stdlib/mock cold 与 SOURCE-only overlay 通过，child/network/pip/数值导入均未执行；runtime 子片独立 26+26 是继承。runtime 审 review_historical_n0_runtime_source_20261019T1311 M ef960b8388f991513bbb4f557a342b801a2cee5a0ddf61f4981f7d96919852a9 / S 3a23c5e12cc309e81577cfc68be100dc36de092b6583010077955106df4e4c24；总 SOURCE 审 review_local_n0_historical_probe_source_20261019T1315: MANIFEST.json 1088 B / 8c92ad8835d4517a770ed11ccccd7ce67b369c29af0cd9fe6c077eb12407af51; SUMMARY.json 4563 B / a8316aeae7f24e110740413dcccc7d4e3b996707d6517cb9e99e732ab2c29f85; SOURCE_GO_LOCAL_ORIGINAL_HISTORICAL_N0_REFERENCE_FOUR_STAGE_ONLY。
- 状态 TEMP_SOURCE / actual NOT_EXECUTED；仅源审通过后父方唯一执行一次本地资格 probe。此批无 workflow，不触发新的 Host/native 作业；普通 guard 可运行。

## 2026-10-19T1320 本地 historical 原 N0 参考资格实际通过（安全证据）
- 原源提交 b507977022695113de2070f2a214f32189aeb582，本次为 dot 云本地探针，没有 CI run URL；原 outer exit0/59.096539 秒，协调器 58.951018 秒。四阶段固定 wheel/离线安装/raw2 只读/原参考均 natural0、无超时、cleanuptrue，原参考 6.400553 秒。
- 原 historical Python 与 CI ci31214 身份分列。安全枚举自然 AVX512/expected AVX512；原 n0_reference 报 PASS_FROZEN_N0_EXACT，原 BF16 与 FP32LE 双 SHA 报告均 true。原冻结值为 393216 B/bd41672e6ea7d12746b41e56d21b3309369ecfd87cc26319ae6adbf0874e5cf2 及 786432 B/3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f；原算术/五库/自然能力/线程/双 SHA 门未放宽。
- 固定父门同时要求四阶段清理成功、原 PASS 收据、RSS、FP32LE 新重读及 source/raw2 后验；leader RSS 采样 300024 KiB，限1572864 KiB为观察验收且不含后代。writer 不冒称独立复算或成功 BF16 文件重读；独审已核私有 FP32LE 的全196608低16零/有限位，高16反投影 BF16 精确 bd41672e；五库/historical Python/四源码/两raw/11wheel 重hash同，不称重算参考或另存原生BF16重读。
- raw2 是既存 789504 B 同资产只读资格，本次未重新获取 raw2、不动原目录；收据不冒充 CI same-job 下载。local_reference_qualified=true，baseline_adopted/DUT/fullblock=false，不授 RTL N0 数值或 fullblock PASS，不回填历史未知 ISA，不改变既有 AVX2 拒绝事实。
- 父记录的更早 bwrap 环境初始化失败未启动用户代码，START/log/output 尚未创建，故不算 native 重试；本次原 invocation 是唯一实际计算。600work+120安全尾和无自动重抽保持。
- 实际独审 review_local_n0_historical_actual_20261019T1326，MANIFEST.json 848 B / 73979f6760b463d612bbbcc4176e1bd0fcbe653d436a773e49ccfe7a3f8e1277；SUMMARY.json 5431 B / d01bc4c5a43eff0248ee4ae4854dfed849cf1c31ae30bcbc5811f7acd4fc1b2d；ACCEPT_ACTUAL_LOCAL_ORIGINAL_HISTORICAL_N0_REFERENCE_EXACT_ONLY；仅三原安全 JSON、README 与计划完整 replacement，私有 array/runtime/log 不上传。无源码/workflow 变更，不触发新的 Host/native 作业；普通 guard 可运行。

## 2026-10-19 本地 N0 续接资源缺口与固定工具来源准备（纯说明）
- 本地原historical参考已获有限实际资格；可复用的16输入94920448 B、同SHA SV76366612 B与iDMA原ZIP9926876 B只读身份已有核对，具体固定pin见local_continuation_plan/SOURCE_PINS.json。旧CI same-job收据不冒用，ZIP须按现ready_o+valid_o派生重新提取。
- 当前限定检索缺可验证backend/完整473树/真实模型，PATH中autoconf/autom4te/m4/flex/bison缺失；须按原Verilator revision、唯一seqnum补丁、五官方包/67选定成员、真实工具微例与新构建恢复，不能用历史binary或mock头替资格。顶层VHostBlockTop和cluster真实参数/链接门保持。
- 比较器当前硬选ci31214；未来独立historical adapter只改profile绑定，原五函数/FP64归约/196608/finite/原容差和exact分列不改，本批不混入未审代码。既存资产本地入口与真实单RAM/B退休→ACK0读回仍需有限SOURCE后继。
- 13:36:49Z MemAvailable7998820 KiB低于原8388608 KiB门，差389788 KiB；cgroup限额不可见，不授硬内存保证。原8GiB内存/3GiB磁盘门不放宽；runtime与wheel的tmpfs迁移/删除仅proposal，等待用户明确答复，未动现物。
- 历史39232100796 make451.755421+gen123.743956+compile56.433910=631.933287秒；37阶段858.346829/协调870.427722仅参照，非当前ETA。累计RUSAGE_CHILDREN RSS不作阶段实测峰值。成本只读审PENDING。
- 本批仅固定来源/必要变更/资源缺口说明与计划完整replacement；没有新增测试、下载/安装/搬迁/Host执行，没有workflow变更，不触发新的Host/native作业。普通guard可运行。

## 2026-10-19 13:49 UTC：固定工具计划与 historical 比较器纯 SOURCE 小批
- 本批仅保存两个独立来源片：固定 Verilator/五包续接计划，以及显式 historical profile 比较器候选；不改 workflow，不启动新的 Host/native 作业，不搬迁或删除 runtime/wheels。
- 工具计划沿原 revision 4e194cc3ec8e27b18e17f80d7f99c15f984bbdae、473 原文件、唯一 seqnum +13 B 补丁、五固定包与 67 原始 data 文件。真实本地 roots/四行 cfg/调用路径/ELF-Perl-编译器闭包和新 receipts 仍 UNBOUND；新 bootstrap 尚未由本批实现或授予实际资格。
- 原 8 GiB 资源门、Host AS 6 GiB、单核与共享 6600 秒不变。工具的 205 项是作者保存的既有 SOURCE/mock 记录，独审核来源与输出但未重跑；本地 runpy harness、机器库存、原日志和临时夹具不发布，也不称可搬迁 same-buffer 新入口。
- 工具计划有限审 ACCEPT_LOCAL_FIXED_VERILATOR_SOURCE_PLAN_AND_RECORDED_COLD_ONLY：MANIFEST 168 B / 4069ef8f2229492de1763becf3f3e92f96188437cf32dec5cb4aac3caec18e46；SUMMARY 2363 B / 75a9d15cf4177849cdaf81ebd84831f388a55df8b30c9feda0641467531034a0。
- 比较 worker 唯一将 ci31214 选择改为既有 historical；launch/test 只联动原件 size/SHA。原五比较函数、FP32→FP64 NumPy 归约、196608 值/B 退休/ACK0/完整 capture 门、max_abs≤0.03125 与 mean_abs≤0.005 均不改；numeric_pass 与 bit_exact/hash_exact 分列。comparator 直接校验 FP32 参考，上游原 reference 的双 SHA 资格不被冒称为新双文件比较。
- 比较器有限审 SOURCE_GO_ISOLATED_HISTORICAL_N0_COMPARATOR_BINDING_ONLY：MANIFEST 3086 B / 7ce32313dffbfef61cef408f528a88af9888e8c049fff0b05d163c8f6247a8e2；SUMMARY 2697 B / fff46429a3bfcc51cb58e74eb4201472ad1469337ac95d244fe858132417bc6b。独立搬迁普通/-O 各 49 项、loader 各 6 项及默认 launch 两模式均通过；只有 stdlib/mock，没有实际数组比较。
- 两片仅 TEMP_SOURCE；现有原 CI comparison/reference/PINS 与主作业未替换，historical 本地参考资格仍不能替代工具、资源或 DUT 数值资格。本批计划按已核父文档完整前缀加此纯尾整体替换，绝不追加完整旧文档。

## 2026-10-19 14:14 UTC：固定五包本地 bootstrap v2 的纯 SOURCE 小批
- 本批仅持久化独立 bootstrap 的10件安全源码/说明及本计划纯尾，不修改 workflow，不启动新的 Host/native 作业，不获取或读取真实包，不安装、迁移或删除 runtime/wheels。
- 原 v1 两项 HOLD 保留：F01 固定合法文件名加号被误拒；F02 acquisition receipt 验后另读导致消费 buffer 脱节。v2 仅限固定 catalog/绑定身份的 leaf 支持加号，parent/work/repo 词法保持严格；原 postflight 单读取锚改用已验 bytes，其他谓词原样，结束仍复核 receipt 原 pin。
- SOURCE_GO_LOCAL_DEPENDENCY_BOOTSTRAP_FIXED_COMPOSITION_ONLY：MANIFEST 1887 B / 1be3fceced5a6743c146f6d91f89d49b5a332d9088d6984f11eab60624f3ba01；SUMMARY 3700 B / 97056a036e0f4d33f782d79b39a5f4bcb2bb508eee81e695966a11c014562652。原反例双模式闭合，独立搬迁25+25通过；作者原目录/搬迁25×4与入口6×2共112组记录保留，入口6×2未由独审重跑。
- 八份 repo-relative 底层来源、五固定官方包、67原data与四行cfg relocation保持。work_root/system_programs/native_profile三项为null，schema固定；真实工具/系统库绑定、native probe及same-job backend/Host尚未取得资格。COLD原PENDING标签是作者冻结时记录，README另列后续独审身份。
- 原473源、seqnum唯一补丁、make -j1、8 GiB Host准入、3 GiB磁盘门、原AS/单核/共享6600秒均未改，未来bootstrap只能消耗原预算。SOURCE检查、argv构造、静态profile或可执行副本不等于实际授权或兼容性PASS。
- 只发布最小10件安全文本；不复制底层八来源，不上传本地日志、反例输出、机器库存或搬迁测试副本。完整计划按父205211 B精确前缀加此纯尾整体替换，禁止重复追加全文。

## 2026-10-19 15:52 UTC：获批本地依赖 copy-verify-delete 的安全摘要
- 用户明确批准后，父先复制并核验两棵 runtime/wheels 的 SHA、结构与 mode，再删除旧重复两树。共15,579普通文件/1,010,352,549 B；runtime15,568文件/794,446,463 B，wheels11文件/215,906,086 B，保存的源/副本库存逐字一致，原根其它资产记录保持。
- 旧 wheels 目录0500初次拒删时runtime已删；恢复仅为该待删除私有重复目录增加owner写位，副本目录保持0500，未改系统权限。引用检查的无引用/无错误结果仅覆盖当前proc namespace。
- 15:49:40 UTC 的 MemAvailable=8,907,320 KiB达到原8 GiB门8,388,608 KiB；这是时点快照，后续阶段须重新验原门。没有Host运行，实际N0尚未完成，不授数值/full-block PASS。
- 原证据MANIFEST932 B / aa06b04084c7ed459cf9240075037faecc5e21ac88c111c9a3fc144029e427f2；独审ACCEPT_AUTHORIZED_LOCAL_RUNTIME_WHEELS_MIGRATION_ONLY已闭：MANIFEST569 B / 6c9608f773de977627d3295d16ea2d20b71d9a39757017ba5c59c7eb7865d040；SUMMARY3094 B / 7182ad672508917a1670e6b8432abd67ead8224b96f970edf6d49ece6c318d6c。当前磁盘副本全量hash/结构/mode、旧树缺席、保留六子树/raw2/FP32均独核；迁移前观察及引用扫描仍归父保存记录。仅发布最小safe summary、README和本计划，不发布绝对机器路径、逐文件库存、数组/依赖/log内容，不改workflow。
- 本投影只读保存记录，未触碰两私有树。完整计划按父207063 B精确前缀加此纯尾替换，禁止追加完整旧文档；本后继仅填正式审身份，原迁移证据不改。

## 2026-10-19 16:02 UTC：显式本地 binding observer 与只读 profile 的 TEMP_SOURCE
- 本批独立保存10件安全源码/测试/说明：只读构造真实非null binding，沿固定七个系统程序、五个已pin官方包及原67-member parser；不下载/安装、不创建work/stage/tools、不运行包工具/Host，不改workflow。
- 必须显式选择 original-ci-uid0 或 local-readonly-mount，无自动fallback。原CI UID0分支保持；独立本地profile以精确namespace映射、固定有限目标、同fd只读flag、最长覆盖mount及前后inode/bytes/mode核验提供有限证据，不把UID65534推成宿主UID0，不授系统镜像供应链或ABI/symbol-version资格。
- SOURCE_GO_EXPLICIT_LOCAL_BINDING_OBSERVER_AND_READONLY_PROFILE_ONLY：审MANIFEST4029 B / b6783d0893b0aee06a0143d7e39eaafcff977d4ed347c9a209ce88f0ebd64db4；SUMMARY4121 B / ce464f7444822fe6e31644ae84cc3a6ffeaec750324356d3e44a5e3044a92dda。绑定最终8124 B / 5479837da040462ce5be566dcc4ebeaa74536dbb733fab439663a9181ecb7534来源manifest，早期预读身份不当最终证据。
- 独立搬迁9+9与入口9+9通过，另对10个真实profile目标文件两模式只读静态验证及目标mount/namespace/inode漂移拒例；无关mountinfo变化不导致误拒。作者54组记录另列不混计，原COLD冻结PENDING标签由README说明其后审结果。
- 私有binding/profile/实际JSON、机器路径与逐文件库存、原日志及搬迁副本不公开；只保源码固定合同/公开来源pins和有限结果。后续caller与原生有限probe仍另审，原473源/seqnum补丁/make-j1、单核、8GiB/3GiB门、AS和6600s共享预算不变，N0实际尚未完成。
- 本计划按父208712 B精确前缀加本纯尾完整替换一次，禁止追加完整旧文档；本批未启动任何新的Host/native作业。

## 2026-10-19 16:08 UTC：本地固定五工具 caller 接合 SOURCE（独审通过，实际未执行）

- 在已发布的本地显式只读 binding/profile 与 bootstrap 之上，保存独立 local_toolchain_caller 源片。原 adapter 8776 B / SHA256 5b21cf3d8969873b3d751f52d64dc7e9528edc0a7d68ce3b91d88f65c8ca3896；固定源清单 MANIFEST 5223 B / SHA256 3bda09357935defbded3c6b3cf3a226739fd92fda7a05251f38f7f4ba5ee175c。
- 有限接合只涉及私有五工具真实 invocation key、环境、命令首项和每阶段前后身份核验；不以 /usr/bin 五工具别名冒充，也不回退系统五工具。prepare_tools 原函数逻辑不改，仅接已审 local profile 的 native checker；真实复制或执行另行授权。
- 原 473 源树、seqnum 单项补丁、固定包及头来源、6600 秒共享墙钟、单核与原 8 GiB/3 GiB 准入保持。调用方 bind 后的 run 仍须经原监督 callback；本片不创建实际 stage、不构建或运行 Host。
- 作者 38 项均为合成 mock（主冷测 7×4、入口 5×2）；独立搬迁主冷测 7+7 与入口 5+5 另列，不重复合计。每个主冷测运行中的原十个工具探针由合成 callback 驱动，不能当真实工具资格。原 COLD_RESULT 的 PENDING 保留为形成时状态。
- 本片只保存九份安全源码/说明，不含实际 binding/profile、私有调用路径、机器库存、日志或依赖数据。native 与 N0 数值仍 NOT_EXECUTED；无 workflow 变更。全文按父提交 c1dfb4e01870e206d1dc9f5b3e02c7c123aed6cb 的 210548 B 精确前缀加本尾一次替换，禁止把全文再追加。
- 正式 SOURCE 审查 review_local_toolchain_caller_source_20261019T1606：MANIFEST 2890 B / SHA256 d97924a79077d65691e90f0530e908e5e1925d1c395479e06d39e88e40acde6f；SUMMARY 3685 B / SHA256 66f7c95408030ed958b189f81a4c00281a1c0211ac9559da1bbfe4a1df3b033a。结论 SOURCE_GO_FINITE_PRIVATE_TOOLCHAIN_CALLER_ADAPTER_ONLY；未来缓存接收、真实 stage 与资格化监督入口须另审，本轮实际仍未执行。

## 2026-10-19 16:20 UTC：固定五工具低资源资格化 SOURCE（独审通过，实际未执行）

- 新 local_tool_qualification 源片连接已审 bootstrap、显式只读 profile 和私有五工具 caller；只接收已取得的固定五包，不联网或扩大来源。固定源 MANIFEST 6277 B / SHA256 823a6d241672f5eeb266da31700292db1190f3c6ab5c04ae608351182f91cb43。
- 同一次执行合同固定 13 阶段：新缓存字节接收、原 stage_data、原 prepare_tools 三个数据阶段，然后原五 version 与五 generation。前序真实退出/cleanup、same-buffer结果与本次父进程 pin 绑定；旧下载 receipt 仅作固定字节来源，不冒作本次下载或 WNOWAIT cleanup。
- 共用截止为已有截止与开始后 480 秒的较早者；沿用原监督器、单核及各阶段限制。三数据阶段各 60 秒墙钟/40 秒 work 与 CPU/AS512MiB；十探针各 30 秒墙钟/10 秒 work 与 CPU/AS512MiB。首失败停止，无自动重试；原 Host 8GiB/3GiB 准入不变。
- 作者 37 项均为合成 mock/入口守门，实际包未复制、native 未启动。独立另核 28 项（接收 3+3、协调 6+6、入口 5+5），与作者计数分列；原 COLD_RESULT 的 PENDING 保留为形成时状态。未来真实 PASS 只限固定工具探针，不授 backend、Host 或 N0 数值。
- 公开十一份安全源码/说明，排除私有命令、binding/profile、实际路径参数、机器库存、原始日志；不改 workflow。本计划以父 1208dd2071628d7ab0ae1f6ed4faf4101070af72 的 212582 B 精确前缀加本尾作一次完整替换，禁止追加整篇全文。
- 正式 SOURCE 审查 review_local_tool_qualification_source_20261019T1618：MANIFEST 3003 B / SHA256 23a85dfef016c6ce0e62ca5a41d0733416eaf2973310755436a0b6a04bccd5cc；SUMMARY 4040 B / SHA256 ffb6f9ed4e130d3b9201081d459c3bc9f0e100917887f44c76077d56e1dc655a。结论 SOURCE_GO_SINGLE_BOUNDED_PRESET_AND_FIVE_TOOL_QUALIFICATION_ONLY；原 13 阶段/480 秒/单核与入口 argv 已核，实际执行及终态证据仍待父独立准入。

## 2026-10-19 16:26 UTC：本地固定五工具实际资格有限通过（独审闭合）

- 已审提交 2b0f065831d670869753ba06ae7212919002f8e8 的单次本地资格执行记录有限 PASS：3 数据+5 version+5 generation，共 13 阶段自然退出 0、未超时且 cleanup=true，原 waitid code/status=1/0；外层 0 未替代逐阶段终态。独立 actual 审查已接受本次有限事实。
- 实际版本为 autoconf/autom4te 2.72、m4 1.4.19、flex 2.6.4、bison 3.8.2。固定入口通过原有限生成输出断言；writer 只读重核 13 日志的原 hash、5 版本首行与 5 精确 stdout，不重跑工具。
- 外层 5.990563 秒、入口 5.890277 秒分别记录；原 480 秒共享上限及单 CPU 保持。累计 child maxrss 不冒作独立阶段峰值。固定五包接收/stage/private-copy 已到，未联网且不继承旧下载 cleanup。
- 本次通过仅授固定五工具的有限版本/生成事实；未执行生成 C/C++，backend、Host 与 N0 数值仍未开始。原八件证据清单 MANIFEST 1019 B / SHA256 b92989398267369d36f66cdc37c76751ed6a82591c13a410608948dfb7a11de3；原 RESULT 75078 B / SHA256 c4f9e7242b3762b72055c4a87f388286c2b84df0aea3a462b4f637e1004d4cd9。
- 本批只公开安全 summary/README 与本尾，不上传私有路径、binding/profile、库存、日志、生成代码或依赖数据；无 workflow 变更。本计划以父提交的 214641 B 精确前缀加本尾一次完整替换，禁止将完整文档追加。
- 正式 actual 审查 review_local_tool_qualification_actual_20261019T1624：MANIFEST 595 B / SHA256 71668ec6424b76fcd7483a688c4879d620721eefd83947b3286e9f7f63b583c9；SUMMARY 3567 B / SHA256 8cc44a685098d90074096609df24cee51974d690de43a27db3ea216b873837b2。独立两树 273 entries/217 普通文件/10,305,771 B 与固定探针输出、只读 binder 后验通过；没有再执行工具。结论仅 ACCEPT_ACTUAL_LOCAL_FIXED_FIVE_TOOL_VERSION_AND_GENERATION_ONLY，不扩为通用 ABI、头编译、backend 或 N0 资格。


## 2026-10-19 16:42 UTC：显式 historical runtime/reference consumer 的 TEMP_SOURCE

- 本批只保存独立 local_historical_consumer 源片及冷测合同。原CI pipeline、ci31214 frontdoor、reference helper/PINS与历史私有receipt不改；不重跑参考、工具、backend或Host。正式独立SOURCE审结论为SOURCE_GO_LOCAL_HISTORICAL_CONSUMER_ONLY，不把作者或独审mock当实际资格。
- 派生pipeline只将COMPARISON常量选到已发表historical_comparison；31296 B / SHA256 c3885d039b97861b17a29d74e6bf58448873d1ae476dbffa806a22a199b581cd，逆替换恢复原31285 B；27个原函数/类AST一致，run_numeric逐字不变。consumer 10384 B / SHA256 9c484ba21665fc0f0a92845d579e8566d3e538f776bcb9bc027e8904a5258129。
- 总入口须由原historical Python运行；私有runtime/reference/receipt路径三个显式参数受固定leaf、同父、canonical/无symlink和原内容hash门约束，无路径搜索或fallback。真实调用时原helper重hash解释器与五native/四源码；原4466 B私有receipt与完整786432 B FP32参考再验，既有双SHA资格不改写。当前AVX512/build/threads仍由原comparator实际import/postflight验证，不由旧receipt替代。
- 返回front只含inputs/runtime/reference三键，preflight observation独立标记已有reference消费，不填造原五个frontdoor阶段或其completed旗标。原B退休/ACK0、196608全值、shape/finite、0.03125/0.005容差及bit_exact/hash_exact分列保留。
- 全链仍唯一6600秒，120秒尾储备；N0开始须余完整3600秒，前置最多2880秒。prepare前后及调用前余量不足3720则INCOMPLETE；返回原stop-105交原函数再扣15，硬界恰为原stop-120，不重置deadline，原30秒比较预算不变。
- 作者consumer17+17与原numeric/receipt21+21均纯mock；13原件重核，private路径扫描零命中。来源public MANIFEST3289 B / SHA256 1f82e98fcc762433fecf2415f779ec4b0cf7f6ca7d4109b3079a6fcd0c41086b。没有真实runtime preflight、数值import、FP32读取/比较、reference forward或native启动。
- 仅发布12件安全源码/测试/说明及本纯尾，不含私有launch binding、原receipt本体、runtime/wheels、机器库存或日志；无workflow变化。本计划以父bfce2d5907d85df6cc156e9fafa87cd830f5f47b的216652 B精确前缀加此尾作完整替换一次，禁止追加整篇全文。
- 独审SOURCE身份：review_local_historical_consumer_source_20261019T1645，MANIFEST 1426 B / SHA256 8029333009722a4307cd7c01fecbaef68fcaecddbdf92ff3283bc84a4e3c2877；SUMMARY 2392 B / SHA256 215b64c34796a8875e126226b674ca9a8495fcf8d2cdf42dfb2d87d9c5da1a9a。独立搬迁consumer17+17及原Numeric/ReceiptLabels21+21通过，23成员和13原依赖同pin；仅SOURCE通过，整链actual准入仍单独审。

## 2026-10-19 本地 backend→tiny→Host→单 RAM N0 有限续接 SOURCE v2 独审通过
- 新增local_backend_host_n0_continuation的17件冻结安全原件及独立STATUS/SOURCE_REVIEW。四生产件闭合已资格五工具消费、cached FlexLexer原真实g++头探针、17阶段有限协调器与同buffer冷入口；原source473/唯一seqnum补丁/fresh make-j1/tiny4、319双拆块/retained13/4vlt、真实cluster ABI/链接门与原单RAM N0判据不改。现物FIR/SV、ZIP与16原输入bytes只重新核验/纯数据复制，不重走Scala/FIRRTL或43stage前门。
- 同一t0涵盖初始hash和准入：总6600秒、前置≤2880秒、完整3600秒N0窗口、工作≤6480秒、落证段≤120秒且不超总stop；17native之外仅一次≤60秒的16文件94920448B纯数据copy，无数值转换。入口及Host生成/编译/N0前仍8GiB MemAvailable+3GiB磁盘、单CPU；backend AS4GiB、Host/capture AS6GiB、比较AS8GiB，首失败即停、无重试。帽/时间耗尽INCOMPLETE，不能判numericFAIL。
- 五工具复用原13项真实自然0/cleanup资格并每阶段重核当前私有工具/profile；FIFO明确接受已审run39232100796同源码4case/5180的三阶段自然收据与五源pin，local FIFO仍NOT_RUN。原historical参考/runtime由已发布consumer显式私有路径绑定；原参考不重算，当前dispatch/threads仍由原比较器真实检验。
- v1仅F01 HOLD（报告/恢复二次错误覆盖原错）已在独立v2窄修：保首错、固定四项恢复均尝试、报告窗口受120秒与总stop双夹。除run.finally外协调器AST与v1一致，入口仅更新pin；原两工具/header适配逐字不变。作者普通/-O/搬迁双模各135组，共540纯mock通过；独审135+135并继承原capture2/compare1测试边界，不能相加冒作实际测试。
- SOURCE独审：M798/93030e61dae1c6c9d92a06b25866abe4f4ecc59979721bee315d1e0598b8dbb6，S3891/cb4cce9f49ec298c45e299d0415b6c1cf6bf736281052bdc749d06e2b41cdc7f，结论SOURCE_GO_SINGLE_BOUNDED_LOCAL_BACKEND_HOST_N0_CONTINUATION。原件待审标签由独立STATUS准确补最终身份，不热改冻结源。
- 本次仅安全源码/冷测/审摘要持久化，无workflow变更、无本地backend/Host/N0新增实际资格；全链一次执行虽已有条件授权，仍须私有binding、现场原门与原监督同满足。最终成功必须原进程exit0与RESULT及cleanup一致，RESULT在恢复之前写出不能单独授成功。机器路径、权重、原receipt/日志、实际command/launcher与搬迁副本不公开，full_block_pass/baseline_adopted继续false。

## 2026-10-19 17:06 UTC：本地 continuation 早期 INCOMPLETE（独审闭合）

- 单次源提交 a2ba85252bf3f922044e84cf6464da36211c5b51 的 continuation 外层退出 1，整体 INCOMPLETE；四 native 阶段 official_source473、cached header、g++ header probe、autoconf 均自然 0/未超时/cleanup=true，原 waitid 1/0。独立 actual 审查已闭合。
- 保存的 traceback 将父后验拒绝定位到 objcache_configure_witness 的“finite OBJCACHE cache branch”文本锚条件；发生在 autoconf 成功后、configure 启动前。原 RESULT 的 ContractFailure 不被倒填成子进程失败；不推断生成配置语义等价或缓存错误启用。
- 本次未 configure/make、未 Host 生成/编译/运行、未 N0 比较，不是数值 FAIL。外层 19.522997 秒与协调器 19.469299 秒分列；没有自动重试。父 16 输入/94,920,448 B 只是数据复制，既有 FIFO/SV/参考不计本次新资格。
- 原七件证据 MANIFEST 1005 B / SHA256 1df2aeb35058396f0ae93e3808f3fd7f7a6bd6f7b97f35ebfe363b35991cfe26；RESULT 13281 B / SHA256 aa84b58cb1e2a7e7f612c7369ec4a1b0dd25f8df9cb213e57ae611430c397d2a。本批只公开安全 summary/README/本尾，排除私有路径、库存、日志、配置生成物与数组；无 workflow 或执行源码变动。计划以父 222028 B 精确前缀加本尾一次完整替换，禁止追加全文。
- 正式 actual 审查 review_local_continuation_actual_20261019T1700：MANIFEST.json 601 B / SHA256 31b293e9394fe8a25b88c341e5a43816500ea1b6534bced6db41197081507f16；SUMMARY.md 4807 B / SHA256 7a9d23fbacc4c3be6d0467e7624d18638a3f35d9aad331ba8c383ebd8a275894。结论 ACCEPT_ACTUAL_LOCAL_CONTINUATION_AUTOCONF_WITNESS_FAILURE_ONLY，接受原失败证据与有限执行边界，不授后续构建或数值资格。


## 2026-10-19 17:11 UTC：OBJCACHE 精确文本门修复与原473缓存续接 SOURCE 已独审

- 上次唯一有限执行在 `fresh_autoconf` 后父后验首停：外层 1，19.523 秒；前四 native 均自然退出 0 且 cleanup=true，但这不构成 backend/Host/N0 成功。旧输出保持原样。
- 原 gate 只接受 `else $as_nop`。本片仅新增固定官方 Autoconf 2.72 的完整 688 字节 case-e block，SHA256 `f735474b483bdc4f30f18a57d97f3d0c527d692e6434f388dc2bf3befa777722`；单次内存归一、逆变换逐字节一致后调用原 witness。set-empty 缓存命中条件、cached 打印、空赋值和非空 version guard 未变。返回 actual block 的 size/SHA；未知模式仍拒绝，配置后空 OBJCACHE 判据及 make 参数保留。
- 已在场原473完整缓存只读复核为 473 文件、11,747,893 字节。新父数据阶段最多 60 秒，使用原 checked_read/copy_member 同 buffer 写 fresh 树，固定原 receipt 另同 buffer 写入，前后与新旧双树继续原 postflight；不复制 archive、派生对象，不重复网络获取，也不把旧 cleanup 当新 native 资格。
- 此次合同是 2 个父数据阶段与 16 个 native 阶段；fresh header 数据/真实 g++ probe/autoconf 仍需在新路径产生当前收据。唯一 seqnum 补丁、make -j1、tiny、319 双拆块、Host 真实 ABI/链接与单 RAM N0 判据继续原实现。
- RESULT 新增两项安全合同字段：只消费原精确 ContractFailure 类型及原 boundary/code 词表，未知 null，不带任意异常文本。原首错误优先和 restore 规则保持。
- 原唯一 t0 总 6600 秒、前置截止 2880 秒、完整 N0 3600 秒和最多 120 秒落证保持；原单核、AS/CPU/FSIZE、四处 8 GiB RAM/3 GiB disk 门不变。launcher 仅更新命令身份字面量，首行 t0 和外层 TERM6590/KILL5 保持。
- 新定向冷测 normal/-O/搬迁 normal/搬迁 -O 各 54 项，共 216 项，全部 exit0/stderr0；独审另作空 cwd 搬迁 54+54 与保留 actual configure 文本正负检查。旧 540 项是继承证据，本片没有重跑或包装成新结果。
- 独审结论 `SOURCE_GO_SINGLE_BOUNDED_OBJCACHE_CACHE_CONTINUATION`；review manifest 1273 字节 / `446f788841d55a12be02fb160e1e252879eda3142cc6fa94f19039cf2e336f8f`，summary 5176 字节 / `d55027265fb80dff88f46a11119d0c65491c65c759f151cd0dc59afba48adac5`。公开仅 `local_objcache_cache_resume/` 下 12 件冻结安全原件和 2 件审状态文本；private binding/launcher、原日志与实际资源路径留本地。
- 这是 SOURCE 与只读旧 bytes 的结论；未因此宣称后续构建或数值通过，`full_block_pass=false`、`baseline_adopted=false`。正式实际仍仅按独审完整合同、现场准入与父唯一受监督调用执行一次。

## 2026-10-19 18:24 UTC：本地首个 M128 N0 完整数值通过（actual 独审已接受）

- 原单次执行源提交 7cc11def3e4e1bb2d6bf6ff15bc1506c607cad6c，outer=0，16 native 自然 0/未超时/cleanup=true，完成 fresh backend/tiny、Host 生成/编译、首 N0 捕获与比较；原 RESULT 为 PASS_FIRST_N0_LIMITED_TOLERANCE_ONLY，独立 actual 审查已接受首 N0 限定容差通过及本次 exact 捕获。
- 单 RTL/单 RAM 桥 2,956,951 cycles，1 launch、12,288 成功 B 退休、ACK0=1 后不再 eval，完整写回/读回 786,432 B、196,608 值，[1,128,1536]；原 8M 探索帽未耗尽，2,428,928 只保归约下界。原 max_abs≤0.03125/mean_abs≤0.005 容差不变，本次有限值 max/mean=0、different_elements=0；bit/hash exact 单列 true，实际与原 FP32 参考 SHA256 同为 3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f。
- 生成完整 2,285 B 日志零 warning/error/unparsed；wrapper 18 入/2 出、单 library target。root header 5,296,945 B 重读成功但仍 UNRECOGNIZED_SYNTAX，256 handle UNKNOWN 不倒填。FIFO 4/5,180 仅继承 39232100796 同源前提，本地 NOT_RUN；既有 historical 参考未重新 forward，固定 SV 未重新发射，原参考能力槽仍 NOT_COLLECTED/UNKNOWN。
- 外层 3,697.674051 秒、协调 3,697.613124 秒；N0 native 2,904.533148 秒、比较 8.378398 秒为嵌套阶段计时。16 输入 94,920,448 B、473 源码 11,747,893 B 为父数据复制/重验，不授新的网络获取或 frontdoor。只首 N0 限定数值 PASS；full_block_pass=false、baseline_adopted=false，后续数值阶段和完整 block 未通过。
- 原七件证据 MANIFEST 1005 B / 02be7877f6a10dbb08ebd5e6e2d565366278db9642aacb3f5d24240595e18ad8，RESULT 37258 B / 3b41e48ddcc58f109c0bf8b58cdd9777a0573c47617d462e0e49d4957e56c13d。本批只安全 summary/README/计划，无 workflow；排除私有路径、数组、库存、raw logs、生成源码与 ELF。计划以父 226603 B 原字节前缀加本尾一次完整替换，禁止追加完整文档。
- 正式 actual 独审 review_local_objcache_resume_actual_20261019T1818：MANIFEST 613 B / fa5e5b952a92fb1fe6604237c04221279c26a76990e8c5bc0153b59e434a8b22；SUMMARY 20581 B / af34169bb8291ee49510be82ea6332d9aed928a707f010b0fc990a2ba1ee0fe7。完整 196,608 FP32 字只读逐位一致、零非有限/低16非零/尾随字节；上16小端反投影 BF16 393,216 B / bd41672e6ea7d12746b41e56d21b3309369ecfd87cc26319ae6adbf0874e5cf2，与原 native 参考身份相同，没有新 forward 或模型回放。
- 周期单位为每次 scheduler 主高沿 observe_counts，含工作 edge0 空闲、edge1 launch 至 ACK0，排除 4+4 reset 高沿；128 项 core-state 和为 2,956,951。AXI stall 按通道 pre-edge valid&&!ready 计数且可重叠，不相加作额外周期；useful-MAC 分子未建立，不报利用率。此前 session8356 原失败保留，首 N0 之外资格不扩大。


## 2026-10-19 18:47 UTC：PC1 无 bias qraw 双轨参考核心 SOURCE

- 本批公开独立pc1_reference_models核心源码/合成冷测与安全说明；PC1定义为M128×N1536×K1536的n0×wq，无bias、无BF16输出舍入。已有27-stage仅冻结带bias/BF16的qr，不能替代qraw或由qr减bias构造。official_raw_numeric_pass、application_accuracy_pass与typed_recipe_bit_exact_to_rtl均为null。
- 独立数学轨用9×uint64正/负superaccumulator，逐项精确BF16乘积按2^-266单位累加，末尾相减，再直接RN-even投影FP32与FP64；1536项/抵消及196608误差总和均有576bit容量证明，不用Python逐MAC或FP64近似累加。此为自建数学oracle，不称官方已冻结无bias payload。
- typed轨逐byte消费原dot16.inc，固定K[0,1024)+[1024,1536)、pair高先低、逐项FP32 fused FMA、独立partial合并。对应router/k-window/slot/HardFloat/独立FP32 add原源；无bias、无BF16输出物化。两个轨道分别保留，typed匹配不能单独代替数学精度。
- 固定独立n0 786432 B/SHA256 3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f；wq 4718592 B/SHA256 ad7ce2dae58deb01656348a6ee2bd6919ed6c2bc83f31b88eed75381cd718b72。既有同RAM实际N0只作身份相等门，不喂入参考、不恢复旧进程或改写旧收据。
- 合成例覆盖一般FP32融合差异、合法BF16渐进下溢融合差异、1024/512 partial、pair顺序、bias/BF16污染、正负零/次正规/RN-even/overflow。后继完整196608输出将报告精确绝对误差整数、bit-equal、ULP全桶、相对误差向外区间；解析gamma1537+underflow界预冻结且只作诊断，不继承N0容差或按DUT结果调阈值。
- 来源MANIFEST 3693 B/SHA256 8036848dcfe00eff172977cfa4a181b78d7aa02916ef8a175e003901029d93fe；25成员70770 B、21原源码同pin，原dot16/SHA头不改。作者普通/-O/搬迁两模各29，独审普通/-O各29通过，均纯整数/Fraction与mock，无实际数组读取、native编译/运行、Torch/NumPy或RTL。
- 独审结论ACCEPT_PC1_TWO_REFERENCE_MODELS_SOURCE_ONLY：review_pc1_reference_core_20261019T1844，MANIFEST 550 B/SHA256 161b9e043efcbcc89ec4c85ccf637559c62e0315578c417356752ffafdb7cdd2；SUMMARY 3927 B/SHA256 a880263eae21d76de8293d7d084238f9ba7675f0e22189e101a8e1d2e2d09a0d。当前TEMP_SOURCE/NOT_EXECUTED；三阶段210秒/单CPU/512MiB预算仍须固定依赖和最薄监督入口/精确命令独审后实施，长RTL未授权。
- 本批不含私有binding、runtime、原receipt、实际数组或原日志，不改旧N0 PASS、生产或workflow。中文计划以父343ff1b3f8516ebb0ce7c8e8762e44506fb76ab7的229542 B精确前缀加本纯尾作完整替换一次，禁止追加整篇全文。


## 2026-10-19 18:51 UTC：最小 PC0→ACK0→PC1→ACK1 桥接 SOURCE 独审闭合

- 新增隔离 pc01_bridge：39 件原字节安全 public 文件、28 件生产源码、44 项原来源 pins，加独立最终 STATUS。原 N0/RTL/普通 archive 与已退出实际进程均未改动；本片未 C++ 编译、未运行 native 或 RTL、未获得 qraw 数值结果。已有 N0 actual PASS 保持原范围，不转移成 PC1 通过。
- 新入口从 fresh reset 开始，在同一个 Host/context/root/Syms 和同一 RAM 中完成 PC0、真实 ACK0，再继续 PC1。原 N0 scheduler/adapter 保持存活；PC1 私有固定 permit/generation、接受的 Dense job、qraw AW/W/B 账本和全覆盖共同授写。qraw 的 786432 B/196608 FP32 字只有完整退休和 ACK1 后发布；post_pc=2/jobs=2，终 ACK1 后零次 eval，无 PC2、bias 或 BF16 输出转换。
- 读权限只消费实际 command/descriptor、Wq 与同 RAM 已发布 N0。模型/AXI/Matrix/共享 vector 检查在 B mutation 前完成，随后仅 noexcept 退休。现有注册边界能观察公共 job/done、共享服务、Matrix 与 AXI；未新增 RTL tap，也不声称直接观察所有内部 reduction tile/window。内部资源退休依赖固定原 RTL 语义与外部无债终态，独立数学和 typed 两轨结果仍由各自模型批提供。
- 修正后的 transposed issue 为每次128×32、sliceMask=255；160列对应5个 context，末96列对应3个，wideSteps=(9×5+3)×1536=73728，sliceSteps=589824，executed/useful MAC=301989888，binary-add vectors=12288。8×16-row 是输出遍历，不是额外 issue 组。PC1 分母固定4096×(ACK1高沿−PC1接受高沿+1)，涵盖完整加载/计算/合并/写回/stall/退休；whole-PC01 总周期另列，不能称 whole-block 利用率。
- 全 PC01 8M 主周期探索帽包含重新执行 PC0，不保证 PC1 完成；不足则 INCOMPLETE、不写部分 qraw。普通 archive 加三个 runtime object 和固定 header 共19项现物仅只读复核；预备命令只在 fresh 目录编译一个 driver 并链接，不调用旧 Makefile、不重新生成 RTL。建议编译链接120秒/单CPU、8GiB RAM与3GiB磁盘门及6GiB地址空间仅是待绑定计划；完整执行监督入口、墙钟及参考比较仍未获此 SOURCE 结论授予。
- 作者纯冷42普通+42优化+42搬迁普通+42搬迁优化，以及same-buffer入口9普通+9优化，共186项通过。独审另作42+42及入口9+9；测试消费固定size/SHA的同buffer源码，覆盖全qraw抽象账本、权限/退休/ACK与入口同长替换、长短、遍历和symlink拒例。Python抽象ledger与静态源码检查均不代替C++接口、RTL或数值资格。
- 根 SOURCE manifest 6527 B/SHA256 f8f0ab2c27c677dd01f8e294856b855f8cc6133b472816c0c504a76cdff9829d；生产manifest4472 B/40ebb6c1957941b90906c4dc5c0d561816fa413aa5a4431a1bd2d191f39dc5b1；COLD_RESULT2195 B/0015d0f71e667d1ec6508c012a28f5543bc8131f88ed46a3dcc35f4e09147eb1。正式独审 ACCEPT_FINITE_PC01_BRIDGE_SOURCE_ONLY：review_pc01_bridge_source_20261019T1849，MANIFEST827 B/f2272142b2c50cf8c1bc41606d2f7194e546013b5ff041c20e8edc634b5e4725，SUMMARY.json4749 B/5d39ff86087bb3dec29855f453cfe38997d30a5db8dcbf9162bacefcd9e52f3e。原README待审文字由独立STATUS提供最终身份，不热改冻结件。
- 本次仅安全源码/冷测与元数据，不公开私有relink绑定、机器路径、数组、实际receipt、原日志或搬迁fixture，不改workflow。计划按父bc0a78b042b253668c2ed79ac6a6bbe0e88c4dcf的232260 B精确前缀加本纯尾，一次完整替换；禁止追加全文。full_block_pass=false、baseline_adopted=false。


### 2026-10-19 PC1 两参考模型三阶段监督入口（TEMP_SOURCE 独立小批）

- 本节只持久化执行入口的 SOURCE 资格，沿用已审独立数学与 DUT-order 两模型；本批冻结时 native/full 为 NOT_EXECUTED，后续 actual 证据与结论另批记录。本批没有采用任何模型结果为新基线，不改变原 N0 PASS 或阈值，不触发新的 Host/RTL/native 作业；workflow 文件不变，普通 push 的轻量 guard 另记。
- 总墙时 210 秒，compile/micro/full 阶段 total 为 45/20/120 秒，work 为 30/5/105 秒，CPU 为 30/3/100 秒；尾部保留 25 秒。父实际调用还须绑定包含 launcher 与有界收尾的 ≤210 秒外层总界。每个 native child 复用原 fixed_support/run_phase，原 owner deadline、natural exit、WNOWAIT/reap、group cleanup、首错与预算不改。
- 固定依赖门为此次命令的 36 文件、44 alias、16 soname、23 ELF 静态资格；既有 g++ realpath 与原 mount/binding 保留。ELF reader 仅 32→64 MiB 文件 cap 与 1→2 MiB DT_STRSZ cap 投影，并逐字节逆还原；编译 argv 仅额外 -B 到四个固定工具 symlink 目录，PATH/库目录固定。机器路径、私有 binding/命令/依赖清单与原日志不公开；未声称通用系统闭包或实际工具查找已观测。
- v1 有限独审发现 E01/E02/E03，v2 分别补齐恢复动作保首错、所有前门后重核完整阶段窗口、micro/full 后重核 binary。作者 46 例纯 mock 在普通/-O/搬迁普通/搬迁-O 四模式通过；独审普通/-O 各 46 例及原三反例两模闭合。
- SOURCE verdict 为 ACCEPT_PC1_REFERENCE_THREE_STAGE_EXECUTION_SOURCE_ONLY。源 manifest 3049 B / 3b203a08d08b600b98330cd6a70ce6cc290c8bf20089dd0c99a7ccd0f9d76b2d；独审 manifest 887 B / 1e8361e6974bc6d19b169806bf891b62e2e8801b94af1433c4bf19d74c6a50dc；summary 3480 B / fdf44a67eded8289a8e074ff802ab4c21dc7b2b301dbee13ec8526a2f30c5a2e。仅公开 8 个必要原件和安全 README/STATUS；生产与冷测冻结字节不改。
- 该 SOURCE 资格不证明完整 196608 值的实际误差、官方 raw 无 bias payload PASS 或 RTL bit-exact；official_raw_numeric_pass、application_accuracy_pass、typed_recipe_bit_exact_to_rtl 均仍为 null。数学独立性、无 bias/无 BF16 输出舍入、输入 SHA 与 typed 顺序各自保持原已审合同。


### 2026-10-19 PC1 两参考模型完整 actual（仅诊断资格，RTL 尚未完成）

- 在前批已审三阶段入口、固定编译依赖与 ≤210 秒外层限制下，compile、micro、full_models 三个 native 阶段自然退出均为 0，WNOWAIT/reap 与 group cleanup 确认；外层退出 0，耗时 9.802904926 秒，内部协调 9.729834938 秒。三 child native wall 约 1.481360/0.022183/6.316384 秒；145440 KiB 为累计已回收 children maxrss，不能冒充某阶段瞬时树峰值。没有运行 RTL，也未重生 N0 或恢复旧 RAM。
- 对同一固定独立 N0 与原 Wq，完成无 bias、无 BF16 输出舍入的 M128×K1536×N1536 qraw，两轨各 301989888 次逻辑 MAC。独立精确数学轨和 DUT-order 两 partial/pair 高先低/FP32 FMA/second+first 轨分列，三份输出均完整 196608 值且有限；typed 与数学 RN-FP32 完全相同 28700 个值，误差非零。
- 相对精确数学点积，最大绝对误差 2.2658554371446371e-5，平均绝对误差 FP64 近似值 1.7047476303466264e-7。最大 ULP 48576 与最大相对误差约 0.5192690553% 位于零基 row95/col748：精确值 146167/2^32、绝对误差 759/2^32，正负项抵消成近零结果；该点不等于最大绝对误差点。最大绝对误差在 row13/col447，精确误差 389271/2^34、距离 6 ULP。解析舍入界全部满足仅是预定浮点诊断条件，不是应用准确率阈值。
- 独审全扫描三输出的 hash/finite/bit equality/ULP 分桶，并对两点各重算 1536 个精确 BF16 乘积；未独立重复整轨 301989888-MAC。相对已舍入 FP64 导出值扫描得到均值 1.7047476303466687e-7，与精确 accumulator 近似均值差 4.2351647363e-21/元素，在 FP64 舍入界内，两个口径不混用。
- 正式 verdict：ACCEPT_ACTUAL_PC1_TWO_REFERENCE_MODELS_COMPLETE_DIAGNOSTIC_ONLY。actual 原证据 manifest 1138 B / 84d4670ef0413a3afcf9476dcf96b82714e31d6811cf1b3eedafe4f587f0220f；独审 manifest 381 B / b8598654be706a69c38eba26e1913aee52f21b29c76b680ad66c0ad0caf7251c；summary 10373 B / 468969f36d80fe77c8ab778b7a6366932489da2e08d6d455e13a0b96684fa261。只公开白名单数字、公开源码/产物 hash 与安全解释，数组、私有路径、启动参数、原收据、raw log 不发布。
- 允许保留三输出身份作同一 stimulus 的分轨诊断参考：数学 FP32 SHA256 42604d286bb7f237c4dc982b4a65065ea74edec82714a4e0f0ad07fcd6172851；数学 FP64 ef5d02aa4b9ad77afdb61eb2842786780d218978bc1dac4641068ec4856710e8；typed FP32 346b2974824f3e2849206d5ea72f7a066c328439c4faa088bf2a13d742b713f1。后续必须先核输入/来源 SHA、新鲜 PC0 实际 N0 identity、ACK1/B retire 与完整 196608 qraw，再分别比较 typed 与独立数学轨。
- official_raw_numeric_pass、application_accuracy_pass、typed_recipe_bit_exact_to_rtl 保持 null，rtl_executed=false，baseline_adopted=false，full_block_pass=false。原 N0 PASS 保留，本批不把模型诊断提升为官方 qraw、应用精度或 RTL 等价结论；workflow 文件不变，普通 push 的轻量 guard 另记。


## 2026-10-19：PC01 既有普通 archive 的有限 driver 重链 SOURCE 已独审

本次发布 `candidates/host93_first_n0_sources/pc01_relink/` 的 13 件冻结公开原件与 STATUS，只准备既有 PC01 driver 的 compile/link 调用方；未改 RTL 算术、未重新生成模型或构建 backend。来源为已核普通 archive 与 19 件精确依赖，28 件桥生产源码和 44 项原来源继续逐项 pin。私有路径、绑定、库属性观察、机器命令、日志、权重和运行数组均不公开。

SOURCE 独审结论为 `ACCEPT_PC01_DRIVER_COMPILE_LINK_SOURCE_AND_180_SECOND_INVOCATION_ONLY`。独审 MANIFEST 为 842 B / dd3cc28794623ce26a1c62c11202a0b21f06f978149dc2108e8004a3b544833e；SUMMARY 为 4019 B / d92812b4e48c3e3132a7b753fbe3fd77535afdd2231d5628b398da507c9fa854。作者同 buffer 冷入口在普通、优化、搬迁普通、搬迁优化四模式各 97 项通过；独审搬迁普通与优化各 97 项通过。全部为纯 mock，不调用编译器或模型。

重链固定只有 compile 与 link 两个原监督 native phase；输入、源码、原件与副本、对象、ELF、39 项固定系统依赖及 argv/env 均有前后复核。固定 g++、单核、AS 6 GiB、MemAvailable ≥8 GiB 与磁盘 ≥3 GiB 保留。仅新增固定 libatomic 允许项以及该库和两个原 pthread archive 身份；ELF parser、只读 mount 信任边界和原监督逻辑不改。首失败停，原异常优先，未知安全码为 null。

重链单次总墙钟上界 180 秒，含初始 pin/准入、95 秒 compile phase、25 秒 link phase及 30 秒落证；外层 TERM 170 秒、KILL 5 秒、尾 shell 5 秒仍在 180 秒内。该入口仅验证产生 ELF 的静态身份，不执行 PC01 ELF。SOURCE 准备本身未 C++ 编译、未 native、未 RTL；独立实际结果另依冻结收据审定，本发布不推断其结果。

后续单次 fresh PC0→ACK0→PC1→ACK1 执行另设自己的 t0，预算最多 10620 秒，和独立重链 180 秒合计上界 10800 秒；两步等待不计仿真 wall，不冒充同一 t0。8,000,000 主周期是总 cap，不能保证完成。原 N0 2,956,951 周期的协调墙钟 2904.533148 秒与 native 墙钟 2904.369166 秒分列；按原速度推算仅是预算参考，不能替代未知 PC1 吞吐实测。长执行合同与三轨比较另审，SOURCE 结论不授予长 RTL 或数值通过。


## 2026-10-19 PC01 驱动复用原 archive 的实际编译与链接

已完成唯一低资源两阶段资格：新 PC01 驱动编译与原 Host archive 链接，原 native 墙钟分别 3.459783 / 0.144490 秒，两者自然退出 0、未超时且清理确认；外层退出 0、总墙钟 5.451080440 秒。没有重建 backend 或重新生成 RTL，没有调用新可执行文件。

新 ELF 13,537,744 B / cb64b5cf1d5e9c226b9768fb3fdcbb3305bee894b6d904cb4cf29633d10fe5b1；原 archive 17,631,506 B / dafcc125c4a4463b9ff454fda6b7a4031bfa17fd98cde1e8386ff058ce245b2f。独核 80 项工作树、47 source/cache、39 固定系统文件与49别名及 .d/ELF 静态链。-MMD 不含系统头，RSS 为累计子进程记账。正式独审 ACCEPT_ACTUAL_PC01_DRIVER_COMPILE_LINK_ONLY；MANIFEST1256 B / 9fc63304848d842ec22d617fc05d5b2bba1413a15c80fd1b2ed797a887d50de1，SUMMARY5665 B / 768474add541e8c033126d02a8f0efbb4bd913fcf6ccaa412bd7f727b9b49195。

后继在独立审查的 fresh 单 Host/Syms/单 RAM 中绑定此成功 ELF/receipt，连续 PC0→ACK0→PC1→ACK1，再作完整196608值三轨比较。两次实际窗口分别上限180秒和10620秒，后者包含比较与落证；中间准备等待不算仿真时间。PC01实际/数值/fullblock均未授通过，五block仍0/5。此次安全三路径只持久化汇总，不触发新的Host/RTL/native作业；普通push轻量guard另记。全部原输入、参考、输出、二进制及证据保留，无清理。


## 2026-10-19 PC01 三轨完整比较只读 SOURCE 已独审

新增 candidates/host93_first_n0_sources/pc01_three_reference_compare/ 的8件冻结原件与安全README/STATUS。生产接口 compare(capture_root, reference_root, reference_receipt, *, shared_stop) 返回数据观察；固定loader对同一已核buffer执行。所有实际路径只由私有caller配置给入，不含数组、私有绑定或raw日志。本批不触发新的Host/RTL/native作业；workflow文件不变，普通push的轻量guard另记。

正式SOURCE结论 ACCEPT_PC01_THREE_REFERENCE_READONLY_COMPARISON_SOURCE_ONLY。独审MANIFEST128 B / 56b6158791820af77740b6691d7e019738be2e0aa682e976339b2c00cdb37e1d，SUMMARY2803 B / bb77658273a04d0ccd1b7794711e99e29f6eb39995045ee2f6ff841101a473ab。冻结源MANIFEST3055 B / a77e371a5a927ca1dd4837eff66c7947310faa09a0a9f1ba7de05d6a5a81f9ce含21成员和16来源。作者普通/-O/搬迁双模式各48例，独审48+48纯合成冷测通过，另核128组Fraction与266项拓宽边界；未读取真实完整capture或参考数组。

消费者沿真实counts的41个顶层字段、15个AXI字段，固定ACK0/ACK1、PC序列、jobs/dones、完整786432字节/196608值及MAC/issue/add计数，交叉核窗口和退休。freshPC0 N0必须逐字匹配3c25077e原SHA；qraw完整且有限。专属qraw B=2048由固定burstWrites、1KiB页门与每行十窗[1,2,1,2,2,1,2,2,1,2]推导，16×128；W beats仍12288。该数不替换N0的B12288。N0内部门与completion payload只由已审driver成功控制流加caller关联的自然exit0证明，不能称为consumer独立receipt观测。

三个参考输出身份独立固定为typed FP32 346b2974…、数学RN-FP32 42604d28…、数学RN-FP64 ef5d02aa…，原RESULT.json1249 B / ae61290bf5ba0d5ff2f21920c8913a15736c788e3093a06ff2c9e0ba89b586f6另核；收据自述不能设定期望。typed全量逐bit/mismatch/hash独立列，数学两轨分别给整数绝对误差总量、近似均值/最大值、完整ULP分桶和相对误差；它们相对RN导出值，不冒充未舍入实数点积全量精确误差。位差仍保留完整诊断。所有七文件同buffer消费且前后重核。

本片SOURCE_ONLY，实际capture比较未执行。official_raw_numeric_pass、application_accuracy_pass、typed_recipe_bit_exact_to_rtl均null，full_block_pass=false，无新增容差。caller须真实关联固定native源、退出0与cleanup及同RAM来源，方可分别汇总typed匹配和数学诊断。函数只读、无child/无timer，≤60秒合作检查使用min(start+60,shared_stop)，不能延长caller硬截止。独立重链180秒和后续长窗口10620秒合计最多10800秒；比较完全在后一个原窗口内，长入口另审。


## 2026-10-19：单次 fresh PC0→ACK0→PC1→ACK1 有界调用方 SOURCE

本批发布 `candidates/host93_first_n0_sources/pc01_capture/` 的11件公开文本与真实SOURCE审状态。调用方读取既有实际独审接受的 PC01 ELF（13,537,744 B，SHA256 cb64b5cf1d5e9c226b9768fb3fdcbb3305bee894b6d904cb4cf29633d10fe5b1），不重复重链、backend或RTL生成。原重链两阶段收据、三阶段数学模型收据与各自身份保持固定；私有路径、精确机器命令、输入和结果数组均不公开。

授权分两步：独立重链最多180秒，本次新t0最多10620秒，合计上界10800秒。两步间等待不算native仿真wall，不冒充同一t0。本次outer首行采t0，早于解释器/命令/SOURCE身份读取；初始检查最多30秒，单native phase10410秒（工作10395、cleanup5、postflight10），三轨比较最多60秒，末尾120秒落证。前验前后均要求完整10410秒phase窗口；不足则在native前首停。报告截止为min(总stop,报告起点+120)。外层TERM10610+KILL5+shell5均在总10620秒内，属于尾储备。原监督仅精确常量6600→10620且逆向复原，未改WNOWAIT、退出、清理、采样和原失败优先逻辑。

固定单核、AS6GiB、MemAvailable≥8GiB与磁盘≥3GiB，native前立即重核。39项系统依赖、28桥生产源码/44原来源、19 archive物件、47重链副本和16项canonical输入在前后重核；16输入共94,920,448字节，无数值转换。新的单一进程从fresh reset真正重跑PC0，保持一个Host/context/Syms/RAM继续PC1，再到ACK1并停止eval；不恢复已退出进程、不加载离线N0替代。8,000,000主周期是全程cap，未知PC1吞吐下不能保证完成。447232固定源粗下界与旧N0速度只供预算分析，不是实际周期或ETA。

监督自然退出0/cleanup、固定argv/cwd与ELF前后身份闭合后，完整比较freshPC0的196608个N0值与原3c25077e…SHA，并核ACK1 qraw完整退休及786432字节/196608值。固定预期wide73728、slice589824、qraw B2048/W12288；B到完整AXI burst映射由既有IdmaWeightBurst源码与有限计数审绑定。ACK0内部writeback与ACK1 payload依赖原固定driver成功路径强门，没有新增内部探针，不凭counts成功布尔授native资格。

PC1有效MAC301989888，分母严格为4096×(ACK1边沿−PC1接受边沿+1)，覆盖整个PC1主周期窗口；whole-block利用率单独保留null。typed参考全196608项逐bit及hash比较；数学FP32与FP64分别输出全量误差/ULP诊断，不新增容差。typed不匹配先保完整数学观察，再首停失败。只有结合真实native资格才可授typed与RTL逐bit一致；official_raw_numeric_pass、application_accuracy_pass仍null，full_block_pass=false。

作者84项纯mock在普通、优化、搬迁普通、搬迁优化四模式全过，另有6项入口负控及同已校验buffer落盘突变后的84项正控。覆盖完整run闭包、前后窗口拒绝、首失败停、typed mismatch保诊断和保存/恢复双故障原异常优先。SOURCE准备未执行PC01；任何后续真实结果另据独立实际收据审定，本批不推断长RTL或数值已通过。

本批SOURCE正式独审结论为 `ACCEPT_SINGLE_FRESH_PC01_CAPTURE_SOURCE_AND_10620_SECOND_INVOCATION_ONLY`；MANIFEST 507 B / c667beeb71a6e9ee7505aa04f8b3dc1d69aca05714ad5993d9d43be9efc66f88，SUMMARY 5741 B / a074cfdf30db32a4bbc2628ac215a02b7b4089c89ef0226417e3069991d3d454。独审搬迁普通84项与优化84项全部通过，精确私有outer与单一10620秒截止已核；SOURCE授权不等同真实运行结果。


## 2026-10-19 单次 fresh PC01 实际终止：PC1_022，数值比较未运行

本轮原outer于19:52:21.295524 UTC开始、20:46:40.793025 UTC结束，退出1/3259.5155213670078秒；native自然退出1/3258.247189秒，非超时且cleanup/reap确认。WNOWAIT为CLD_EXITED/status1，后续清理signal不能倒写退出原因。协调器INCOMPLETE、首异常ValueError/failure_code=null，监督层CHILD_EXIT_NONZERO；132字节原安全诊断为RTL_PC1/CONTRACT_ERROR/PC1_022、numeric NOT_RUN。正式独审ACCEPT_ACTUAL_PC01_CONTRACT_FAILURE_PC1_022_ONLY；MANIFEST380 B / 63fcbb1ec1dfe3ac1ab10ab0a8eb17913b1cf37b27bc23da5e123da37de12e70，SUMMARY9383 B / e53a59e4f085a3616a97ffbfc78bfe5f8354e77994af0a4dccc2473569310824。

capture目录为空，counts.json、actual_n0.f32le、actual_qraw.f32le均未写。固定源在RTL_PC1之前已设完整ACK0退休门（单launch/job/done/ACK、post-PC1、committed/writeback各786432字节、N0 B12288），随后在内存复制N0并计算SHA；这只是固定源及安全诊断支持的控制流推断，没有本轮导出N0 SHA或计数，不能授与原3c25077e…参考一致，也不搬用旧N0周期/PASS。本轮PC1接受、退休进度、ACK1、主周期与利用率都未观测。

PC1_022为8谓词合并identity失败；原诊断未记录逐谓词、周期或调用点。具体失败项与根因UNKNOWN，不把后续静态假说倒填成实际。三轨比较均NOT_RUN，不能称数值不匹配。official_raw_numeric_pass/application_accuracy_pass/typed_recipe_bit_exact_to_rtl均null，full_block_pass=false，五block仍0/5。10620秒本轮与180秒独立重链合计10800秒上界不变；8000000主周期仅cap，未获实际周期，不能声称周期cap已耗尽。

原证据7成员MANIFEST882 B / 9476ed1280b0048f6cbb8261f9ee4b16dcd90b58c30152749a3a2b6370b28db9保留。安全三路径只聚合数字/公开来源身份，不上传原日志、私有路径、数组或二进制，不改原N0/参考PASS。本批不触发新的Host/RTL/native作业；workflow文件不变，普通push轻量guard另记。

独审终止后只读核原7件证据、11项工作树、同一已接受ELF/object/archive、47副本、28桥源、44上游与16输入94920448字节；输入hash已核，数值未重算。这不冒充native失败时未执行的协调器成功postflight或比较。本轮输出仍缺失，PC1_022的8谓词/4调用点仍UNKNOWN。


## 2026-10-19 PC01 identity 首失败固定标量补证 SOURCE 已独审

新增 candidates/host93_first_n0_sources/pc01_failure_capsule/ 的13件冻结公开文本及安全STATUS。只有5件生产文本：新增固定POD/header，窄改runtime声明、driver、PC1 scheduler和main；4件均可逐项逆投影回原件。原8个identity谓词、短路顺序、PC1_022、resetRequired guard、RTL算术、时钟/握手/退休及原资源不变。原实际FAIL保留，具体失败谓词、边沿和根因仍UNKNOWN，数值比较仍NOT_RUN。

新胶囊在原identity require之前冻结，先于RuntimeOwner::checked和adapter析构置Poisoned；四个调用点各有固定site与当前edge。实际求值位由known_mask/true_mask标记，后位为null；独立scalar值不代表对应predicate已执行。root/context有效标志分开，快照不解引用context；root无效时对应模型标量为null。仅取既有注册的owner/router/core/hub/DMA/writeback聚合、matrix计数及已完成的软件jobs/dones/acks/B/committed。HIGH_EVAL_POST端口属于当前已eval高沿，而软件ledger尚未处理该沿，不能混淆两者。聚合状态不自动授予上游首因。

ACK0原强门和已有N0内存hash完成后，仅保计数和32-byte hash；没有额外数组、数值比较或离线N0装载。首失败后原终态JSON仍先输出，随后最多一行固定标量胶囊；固定8192-byte格式缓冲，POD编译期上限1024 bytes。格式截断、短写和flush返回错误只丢补证，原code/exit保留；不把noexcept冒充任意外来异常恢复。成功无胶囊行，root_cause=null。

冻结SOURCE MANIFEST2373 B / 256008b9238d30cba4737079ae2ccdc895b435b9ec85caab25e79384aed3584f。作者49例普通、优化、搬迁普通、搬迁优化全部通过；32个谓词×site组合、31原源同buffer pin、4原件逆投影以及23既有registered字段/8公开字段均核。独审搬迁49+49全部通过。纯Python模型/静态检查不能证明C++编译、真实stdio、RTL根因或数值结果。

正式结论 ACCEPT_PC01_IDENTITY_FAILURE_CAPSULE_SOURCE_ONLY；独审MANIFEST867 B / d881b6b79f5d6b12a6cb3edfe2dfc0b614b410e6f8830338b1663a9c54b6dd54，SUMMARY3638 B / 98eaadea34139d4b584644479fc44cab33dc122b7d4cfbb7dd9955a13bf0c9e1。原28源未来需明确组合24原件+4替换+1新增header共29源；原28-source重链入口不能直接冒用。重链接线另片独审，不以本批SOURCE授C++或actual。

原失败进程已退出，没有checkpoint。任何后续实际须新driver/ELF/receipt闭合并fresh reset重新PC0→ACK0→PC1，不能恢复旧进程或绕过N0成本。本批未编译、重链或长RTL，也不触发新Host/native作业；不发布私有路径、数组、二进制或原始日志；workflow不变，普通push轻量guard另记。full_block_pass=false，五block仍0/5。


## 2026-10-19 PC01 identity capsule 的最小重链绑定 SOURCE 后继（生产SOURCE与公开test入口均已独审）

本片只新增安全SOURCE、纯冷测入口及状态，不触发新的compiler/Host/RTL/native作业。生产run_relink仅CONFIG_PIN、PRODUCTION_PIN、source count 28→29三行变化，逆投影逐字节复原原已审版本；生产launch只改caller pin。24件原桥不变、4件capsule替换、1件新header，组装29源，原19cache身份/44上游pin/39系统依赖全留，staged48。单driver编译并链接同一普通archive，不运行生成ELF，不重建backend或生成RTL。

原两阶段180秒总界、compile95/work80/CPU80、link25/work10/CPU10、30秒尾储备与TERM170/KILL5/尾5保留；原WNOWAIT/reap/cleanup、首失败停与原异常优先函数不变。固定source MANIFEST9105 B/SHA256 0ed658647a5cd1c50829e01195229791eb67e0c07e7bb88aebf69676164bc753，production manifest542 B/a111716b048345c1d69f56cc0289db8b8431df95755b36b5563a0ccc7ec79733；assembled production manifest4632 B/0e6dcab21cec61004b35d6b657456ace9817f7a6be382077e6c2c80bb433ba4a。生产/source/精确outer审定和单次actual各是独立门，本草稿不授native GO。

原101纯mock保留，新增薄入口仅从公开原桥+capsule+本片目录按固定size/SHA读取同buffer，复用原checked/write_exact在可写临时夹恢复测试fixture，再消费原冷入口；不发布29源复制品、私有cache/config/机器路径清单或真实数组。初始Python3.12四模式各101与固定Python3.13搬迁双模各101通过；新增入口独立测试/审查另记STATUS，生产54成员冻结版不修改。

原PC01 natural1/PC1_022证据仍完整保留，具体谓词与根因UNKNOWN，三轨比较NOT_RUN。official_raw_numeric_pass/application_accuracy_pass/typed_recipe_bit_exact_to_rtl为null，full_block_pass=false，五block0/5。本片绑定capsule源码父ef59eb4c52e8b814509fc087def732474ebc223d，按父原文加本节纯尾完整replace；不得将旧完整计划再次append，不能把SOURCE/重链资格写成重放或数值通过。

生产SOURCE正式独审 ACCEPT_PC01_CAPSULE_DRIVER_RELINK_SOURCE_AND_FIXED_180_SECOND_CONTRACT_ONLY，MANIFEST867 B/8c277daab23a327e7855836efec358dad77f8b71589ec950ee426fc4e2e6c615，SUMMARY3506 B/e74c8bd61f1f9575fdbfbae4d65fdf8119b3e8d730de135f1b70c5b25c61c4f6；固定Python3.13独核101+101。公开薄入口作者四模各101及四负控双模拒绝通过，公开入口delta已独审，安全内容审仍独立。已审180秒core/outer不执行，actual须父在GO后单次另记；不授长期重放。

公开纯测试入口正式独审 ACCEPT_PC01_CAPSULE_RELINK_PUBLIC_COLD_ENTRY_ONLY，MANIFEST1399 B/357114cbe5d20be524b3fde1f094b45877a5d19f9a5cfc2774059d9b0ee9385c，SUMMARY1858 B/aba3aee700aa3006782c9fc62efd715f9d70b50212feeff6440cc6d048dc4ef2；独立Python3.13搬迁101+101及4+4前拒通过。新增入口只处理公开source fixture，不使用真实archive/数组/private binding；不扩展生产资格。此次metadata终稿只补STATUS/README与计划审查身份，所有生产/test原字节保留。


## 2026-10-19 PC01 identity capsule 最小重链 actual：仅compile/link成功

本轮于21:21:15.084481 UTC开始、21:21:20.005324 UTC结束，outer退出0/4.92517532799684秒，协调器4.901873234994127秒；compile native2.990941秒、link native0.144842秒，两者自然退出0、未超时且cleanup/reap确认。正式独审ACCEPT_ACTUAL_PC01_CAPSULE_DRIVER_COMPILE_LINK_ONLY；MANIFEST568 B / 13a5456589eaed0e6dfe17cf7652b13d4061a3414a8a35b2d554d3b75c37224b，SUMMARY9281 B / 52f77ba0baff3d7c00ee614334733c216126c6513c81d0fb3f818e6be3a73f3b。

新ELF13547616 B / 73a13d020b99fa78087c639629dcbb8984d3dfbf028baf3adb69b60b51774617，新object1346576 B / 402893a5f11b1bb28b1d3d21545326e2320374715676598b7db7bcd65f3d5c91；原archive17631506 B / dafcc125c4a4463b9ff454fda6b7a4031bfa17fd98cde1e8386ff058ce245b2f不变。未重建backend/生成RTL，未调用新PC01。81项工作树/60普通文件40983550 B，48staged为29候选桥（24原件+4替换+1新增header）及19cache；44上游来源pin保留。

结果只为COMPLETE_DRIVER_COMPILE_LINK_ONLY，capsule无实际运行输出。原session38263自然1/PC1_022与8谓词/4调用点具体UNKNOWN保留，不能从重链成功推断修复、ACK1或数值PASS。三轨比较NOT_RUN，official_raw_numeric_pass/application_accuracy_pass/typed_recipe_bit_exact_to_rtl均null，full_block_pass=false，五block0/5。固定180秒总界、单核/AS6GiB及30秒尾储备保留；337904KiB为累计子进程RSS，-MMD不含系统头。

原7件证据MANIFEST882 B / 80dfbdf526509434586725c6b8c1a367c6905b13e48c378f79a392183a250714完整保留。安全3路径只公开聚合数字/身份，不含私有路径、raw日志、数组或二进制；本次汇总不重跑native/测试，不改原FAIL。本批不触发新的Host/RTL/native作业，workflow文件不变，普通push轻量guard另记。后继fresh调用另审新ELF/receipt与入口资格，不复活旧进程。

独审另核39系统依赖及ELF x86-64 PIE/原5 NEEDED/无RPATH；.d 45 tokens/42 unique=27源+15 cache，只新增capsule header依赖，仍不含系统头。实际开始时core ef59eb4已发布、精确SOURCE/180秒合同已审，而重链安全发布尚pending；不得称从后来的641e6976提交执行。准确新ELF/receipt可供另审fresh入口绑定，本actual不授长执行资格。


## 2026-10-19 PC01 胶囊诊断重放接线 SOURCE 与固定调用合同已独审

新增 candidates/host93_first_n0_sources/pc01_capsule_capture/ 的11件冻结公开文本及安全STATUS；本批只补公开元数据，冻结生产和测试原字节不改。绑定此前已通过实际编译/链接审查的胶囊ELF：13547616 B / 73a13d020b99fa78087c639629dcbb8984d3dfbf028baf3adb69b60b51774617。此资格仅为编译/链接；本批源码准备及出版未调用该ELF。新绑定沿29源、19复用archive材料、48 staged、44上游源码及39系统文件，16输入与三轨参考保持固定。

唯一有限生产增量是新ELF/receipt/config/helper身份绑定，以及在原落证尾窗中观察完整 phases/capture/native.log 的身份。直接复用已固定的support.identity：原1 MiB上限、同fd稳定性和路径前后复核，完整文件保留原位，不取tail、不解析、不复制、不改写、不从hash推断胶囊内容。原132-byte安全首行和可能新增的至多8192-byte胶囊行均属于同一完整原日志；实际是否输出、字段和短路null语义必须在终态后独立读取原日志审计，源码不能先授结果。

日志观察错误只投影固定错误类型，不输出任意异常文本；已有native/父后验首异常保持优先。没有旧异常时，观察失败导致整体失败。观察完成后重核同一report_stop，只给原剩余时间，保存RESULT不另起120秒。完成阶段或比较字段可能在后续观察/保存/restore失败时仍保留；必须结合outer exit、native自然退出、cleanup、完整证据及前后身份，不得单凭RESULT.status授actual。

原10620秒合同、8M主周期上限、单CPU、AS6 GiB、MemAvailable至少8 GiB及磁盘至少3 GiB准入均不变。capture总窗10410秒含work10395、cleanup5、postflight10；比较最多60秒、落证预留120秒。父outer最早计时覆盖命令和源码读取，TERM在10610秒，KILL再5秒，外层落证5秒均在10620内。先前独立重链上限180秒与本片10620秒合计授权上界10800秒，二者各有起点，步间等待不记仿真时间。8M上限不保证PC1完成。

冻结SOURCE MANIFEST3125 B / a9bc98c45d7c2f41a733e4ae7d0186061971f0fb347216290b26c0a035cb2331。作者109例普通、优化、搬迁普通、搬迁优化全部通过；独审搬迁109+109全部通过。包含84例继承纯mock和25例完整日志、合成文件、首错及期限测试；132+8190字节完整日志与相同tail不同prefix反例、1 MiB边界、文件漂移及错误保存路径均核。没有native、编译器、模型运行、网络或真实数组测试。

正式结论 ACCEPT_PC01_CAPSULE_CAPTURE_SOURCE_AND_FIXED_10620_SECOND_INVOCATION_CONTRACT_ONLY；独审MANIFEST1200 B / d721c347563f238f7bcd86d03669e936019e3e689c2828815daf68f14c637616，SUMMARY4414 B / 814a71629f3fbc404352c8435547f12fea7f1e40bd59fc015c0ab6ec4f2dca5f。全部18个候选成员、生产与两层launcher逆投影、精确命令及新实际receipt/ELF前门已核。原件内冻结于审前的pending标签保留，后继STATUS记录正式审结，不热改来源。

后续已授权的单次诊断重放仍须入口资源重核并fresh reset重新PC0→ACK0→PC1→ACK1；已退出进程无checkpoint，不能恢复旧状态或加载离线N0替代。原FAIL保留，PC1_022具体谓词、边沿和根因仍UNKNOWN。本批不包含新capture实际结果，不公开私有路径、命令绑定、数组、二进制或原始日志，workflow不变。full_block_pass=false，五block仍0/5。


## 2026-10-19 PC01 capsule fresh实际失败：首false为reset_required_clear

本轮session4766原outer从21:36:05.679607 UTC至22:27:29.420448 UTC，退出1/3083.745330591002秒；native自然1/3082.526103秒、非超时、cleanup/reap确认。协调器INCOMPLETE/ValueError且failure_code=null，监督CHILD_EXIT_NONZERO。原完整1558B日志保留PC1_022终态和固定标量capsule两行；调用方只核完整身份，未解析内容，以下解读来自终止后原件。正式独审ACCEPT_ACTUAL_PC01_RESET_REQUIRED_IDENTITY_FAILURE_WITH_BOUNDED_CAPSULE_ONLY；MANIFEST559 B / b313ffb6a85497530c70b0dd8512de661cbf380b945b41ee20c94ffb718f53cf，SUMMARY12193 B / f0a69134b4afdb0dc90065e05fc1bdc579f62bbf3f16e0816bf7eba4cba01092。

本轮明确HIGH_EVAL_POST/edge3208723，known63/true31/first_false5；前5谓词true，第6项reset_required_clear=false，后2项context_error_clear/context_finish_clear未求值null。快照先于identity require/checked Poisoned。当前RTL高沿reset_required1、router_bad1、owner_poison1、group_reset_required1，Matrix wide12800/steps102400；其中owner_poison原字段映射owner.sharedPoison组合OR，不是独立owner sticky；这些聚合不自动给FFN或其他上游首因，本轮root_cause仍UNKNOWN/null，不混入未审静态归因。

软件账本未记当前高沿：entry2956951、accept2957107、cycles251772、jobs1/dones0/acks0，qraw成功B响应128个、committed81920字节；B不是字节，ack_edge0因acks0无完成含义。当前RTL与此前软件退休必须分列，不能合成完整PC1利用率或MAC结果。ACK0记录2956951cycles、jobs/dones/acks各1、committed786432/B12288，已有完整内存N0 hash为原3c25077e…；无导出数组或独立导出数组重hash/逐值复核，不能扩大为本轮完整数值PASS。

capture仍空，counts/N0/qraw数组未写；PC1输出不完整，三轨比较NOT_RUN。official_raw_numeric_pass/application_accuracy_pass/typed_recipe_bit_exact_to_rtl均null，full_block_pass=false，五block0/5。前轮session38263具体谓词/边沿继续UNKNOWN，不以本轮回填。原7证据MANIFEST882 B / 0be987ee2a080aadc67839abc7123dfe34d0ed313f7cdeef8c82d4328d0556bc、完整日志1558 B / aaa3df169f16d8f6dc7d7f150ccbea193bec309266cad8288a9be3b0b2a27f84保留。

安全3路径只公开聚合标量/身份，不含raw日志、私有路径、数组或二进制；不重native或测试，不改原FAIL/参考。本批不触发新的Host/RTL/native作业；workflow不变，普通push轻量guard另记。

独审终止后核7证据/11工作树、18源manifest成员、同一ELF/object/archive、29桥源/48 staged/44上游及16输入94920448 B；不冒成功postflight，本次未重hash39系统依赖或重算参考数组。N0/Wq read_bytes为已受理AR请求的完整burst跨度，不代表R beats全退休；251772是entry起已处理周期，不是完整accepted→ACK1分母。ACK0摘要不证明N0随后至失败始终不变，成功后hash gate未到，该项仍UNKNOWN。

## 2026-10-19：原owner合法局部刺激核心SOURCE独审闭合，实际尚未执行

在原PC01 resetRequired失败与更上游UNKNOWN保持不变的前提下，准备独立owner微刺激源码。直接以冻结76366612 B / 2fcc1ba70ad3406b967292624329593aa38e3fe562e9ff3ac675eec100562f61 SV中的QwenOwnerKernel为新top：它是Host实际实例化的同一个无参数已特化module，保真实Router→Coordinator→Dense/Banks→ScheduledSiluOwner→Matrix/FMA。无需Scala/firtool重生成，但仍须新Verilator/C++生成和构建；旧Host archive不能仅重链替代。

固定M128/N1536/K1536、mask255、原tag458753，完整N0 FP32786432/3c25077e…与Wq BF164718592/ad7ce2da…同buffer供数。prefixWorkspace固定原base4507654464、extent786432、generation8，原SV内部splitK=2560，不能误改为partial的1024。partial范围仍由原router给[0,1024)、[1024,1536)，pairReverse=true；不强设内部ng/block/lease，不重算N0、不抽样、不人工回Matrix终端。

外存用单一全局typed事务RAM。固定单64B读只访问原N0/Wq payload，tag/LAST/背压/完整数据保持；写先收descriptor与全部data，再给typed响应。普通memory通道若意外出现即失败，不能零值或伪ACK补齐。它隔离原owner/Dense/Bank/Matrix边界，未包含Host历史与原iDMA/AXI，不把typed响应称ACK1或AXI B。

目标只到ng160 partial1实际首issue：四个精确window请求、前三个partial真实终端/物理issue/done，以及ng0真实求和和128个typed写响应/81920B drain退休全部先成立；wide12801/slice102408只作旁证。请求到达/partial0退休/partial1接收分别记账，不能由12800静态issue前缀替代。首次真实错误即保存有界标量；当前high后RTL与前沿软件退休分列。到目标时job仍可能live，job_completed=false，没有全job终端或完整PC1数值通过。

26成员/17来源及7生产原件已独审。v1唯一F01是终端report二次异常覆盖原exit，v2只固定原exit并保其余6生产逐byte不变；作者显式-I-S-B普通/-O/搬迁四模式每套74主+8loader纯合成通过，独立74+74通过。这些不执行C++，更不是RTL重现。SOURCE身份：review_owner_micro_core_v2_20261019T2306，MANIFEST752 B / 483a3b9cea73de582cb72ba7bb26848d9a4d50b202a3501066270a29ad257d00，SUMMARY1679 B / 09504038c750d4fb6a50263a0647a7c48b219cb8cd61136a9659303b3fdac01d；verdict GO_OWNER_MICRO_CORE_F01_CLOSED_SOURCE_ONLY。生产manifest1019 B / ad587ca4d0ee05953202c5378442bf11e936b2205632a3e2e124a4bbab722475。

未来caller须在实际生成后核196端口与95观察成员的精确名字/位宽，以及原工具/层级/依赖资格；本批尚无这些新生成证据。已定总窗1320秒为生成360、单任务编译600、运行300、落证60，AS6GiB、单CPU，500000局部周期上限；预算是硬上限，不能承诺到目标，首错/超限保INCOMPLETE且不自动加窗。当前生成/编译/native/RTL仍NOT_EXECUTED，official_raw/application/typed-to-RTL均null，full_block=false，五block0/5。

本批只发布核心安全源码/冷测元数据与中文计划完整replacement，不含输入内容、数组、二进制或私有绝对机器路径。不触发新的Host/RTL/native作业；workflow文件不变，普通push轻量guard另记。

### Owner 局部合法刺激的唯一有界监督接线（TEMP SOURCE，2026-10-19）

继 owner 局部 driver 七件修后源码包，本批固定一次 fresh QwenOwnerKernel 顶层 generation → build → run 接线；完整 source/私有命令独审身份在本批 STATUS.json 留档。此处仅 SOURCE 与低资源纯冷测，尚无新生成 ABI、编译成功、真实 owner 目标或历史 Host 故障复现结论。

1. 复用已资格官方固定473 backend、原seqnum补丁与tiny receipt、原SV及319 iDMA/13 retained输入；新job保持307编译源、8 include、4 define及原4 VLT，单独追加已固定owner只读VLT。不重做backend或五工具资格，不把旧Host archive当新owner archive。
2. 原generation命令仅改明确top/prefix/driver/fresh Mdir和追加VLT；原make保持单核-j1、原-O0、固定编译器及空OBJCACHE。原generation census三处、cluster witness四处字面投影都有精确锚和逆变换；原ci_support_v3无源码更改。95新root标量名/类型/位宽和196端口必须在本次生成后实际逐项核，不预先宣称通过。
3. 一次总1320秒从父最早T0开始，环境固定键只传同一原点给私有launcher和同buffer入口。generation360、build600、run300各含原15秒监督余量，尾证据60；全部AS6GiB单CPU，原8GiB可用内存/3GiB磁盘准入。每阶段前后前验均须剩余完整该阶段窗口和尾储备，否则INCOMPLETE首停。父1310TERM+5KILL+5落证将全部加载/hash与执行包在同一上限；未知性能不承诺目标会达到。
4. 原异常优先，完整native.log以原identity作大小/SHA后验、不截tail或解析布尔授成功。native非自然0、cleanup/资源/后验失败即停止。即使保存时已有完成字段，也必须合并outer/native原退出与清理审读，不能只看RESULT status。driver诊断自然0仍须独立实际审读末行；full job/full block=false，历史故障重现及三条精度资格null。
5. 36监督+31caller/入口共67项，在普通、-O、搬迁、搬迁-O四模式合计268次通过，0失败/错误/跳过；每进程AS512MiB、CPU30秒、单CPU。未调用生产run/main或原run_phase，未执行编译器/RTL/网络。这些测试只证明函数级有限接线和失败保全，不作为端到端实际结果。

本批公开12份原字节安全payload、STATUS与本计划完整后继。私有绑定、profile、COMMAND、outer、现物路径和日志只保本地。原Host两次失败与其上游未明边界不变；此局部场景不具有原Host N0前缀或可恢复checkpoint资格。

### Owner 局部首次实际：生成自然成功，后验读取上限失败（2026-10-19）

已发布来源 8b963f58f86d156d4587654b199054f5e09e4fec 的原 session 42131 结束：generation 自然 exit 0，153.944213 秒，cleanup 确认、未超时；完整生成日志 census 的 warning/error/unparsed header 为 0。随后 Python 后验失败，outer exit 1、155.54876243299805 秒，原执行记录 INCOMPLETE。不能把 generation 进程成功或零警告升级成 owner 局部测试通过。

实际 VQwenOwnerKernel___024root.h 为 4,630,258 字节 / a9371ed20684a6b5635de6203918cd33b910d856bd83618cf4a33c9dda398aaf。调用方给 generated_text 的 16 MiB cap 未传入内部 small_read 固定 4 MiB 门，因此原 traceback 停在 ValueError: small read bound。保持原 failure_code/failure_boundary 为 null。census 另一 reader 的 bounded retry 成功，但其 cluster 结构结论仍未建立，不能替代失败的后验；95 观察字段检查未完成，196 端口/cluster witness 未进入。compile、owner native run 均 NOT_STARTED。

原七件证据 manifest 959 B / cecf9a7c0da9c2674198ae18992855afa660d546dc0ec24a7542552d7838a5da；冻结 work inventory 536 项、528 普通文件、8 目录、80,670,440 字节。正式 actual 独审已接受此有限范围：review_owner_micro_generation_actual_20261019T2322，MANIFEST 282 B / d8a40602b4d5a500801f374ec93efc5be7b455fd87ae2a12ab07b01a205c6828；SUMMARY.md 4666 B / c2816c97363998f17e782f19245051cf507f45a8b98543302998cea2438e33ee；verdict ACCEPT_ACTUAL_OWNER_GENERATION_NATURAL_ZERO_POSTFLIGHT_HEADER_BOUND_FAILURE_ONLY。 独审逐项重核 7 件原证据、536 项当前树、39 件源码包成员、7 件 staged owner 原件及 338 件原始源输入（79,657,058 字节）。现物闭合只授有限生成缓存来源资格，不授可搬迁、可编译、ABI 或 runtime 成功；工具/系统依赖与资源准入仍由后继实际入口独立把关。没有 owner job/partial/window/目标 issue 的运行观测，不授原 Host 故障复现资格；原两轮 Host 失败与 UNKNOWN 上游边界不变。official/application/typed-to-RTL 及历史故障重现均 null，full_job/full_block=false，五 block 0/5。

本批只发布 SUMMARY/README 安全聚合及本计划完整 replacement，不带原日志、私有机器路径、数组或 binary，不重跑任何 native/测试，不改原 FAIL；后继 cache/read-bound 修复另审。不触发新的 Host/RTL/native 作业；workflow 文件不变，普通 push 的轻量 guard 另记。

### TEMP Owner 固定header门与生成缓存续接（SOURCE，2026-10-19）

原session42131的generation自然0/cleanup、零warning/error，父因4630258B root header进入仍为4MiB的small_read而失败。原outer1和完整生成证据保持，未编译/运行。本后继只准备固定header读取修复及fresh目录build→run，不重新生成/backend，不冒充本轮生成成功。

1. header_gate仅接受固定leaf、mode600、4630258B/a9371ed20684a6b5635de6203918cd33b910d856bd83618cf4a33c9dda398aaf；复用原bootstrap.checked的同fd同buffer返回，显式16MiB绝对上限，原95字段parser零改。真实header回放通过95项，15×普通/-O/搬迁=45冷例全过。另已只读验证196端口、原cluster seed/seqnum与库图、census与原receipt全同，零warning/error；这些是生成源后验，不授编译或RTL行为资格。
2. 绑定原536项/528文件/80670440B完整库存及正式实际审身份，每阶段前后重核。516个生成obj源/80273076B以验hash的同一buffer复制到fresh obj，源字节不改；无.o/.a/PCH/库输入或hardlink。旧fixture绝对.cpp/-I引用明确作为受核只读输入保留，不能说所有driver输入均来自fresh副本。
3. 原make仅显式top executable，三个-o封住top.mk/child.mk/child.sv生成target，原C++/PCH/archive/link全部保留。-o不继承，但唯一child archive make没有hier include或生成recipe；禁止hier_build。固定继承VM_HIER_VERILATOR=/bin/sh -c 'exit 97'与fresh VM_HIER_RUN_DIR提供额外首错停止，不增加程序依赖或改写makefile。原环境/单核-j1/O0/工具和配置保持，未执行make dry-run。
4. 一次总960秒从最早父T0开始，全部缓存复验/复制/加载计入；build600（work/CPU585）、run300（285）、尾60，AS6GiB单CPU及原8GiB/3GiB准入。阶段前及前验后须剩完整该阶段窗口+尾储备，否则INCOMPLETE首停；950TERM+5KILL+5落证，不延长或承诺ETA。保原first exception/code/traceback与完整日志身份，原generation只标记历史只读复验，不追加native通过阶段。
5. cache22×普通/-O/搬迁=66纯mock通过，与header合计111，0失败/错误/skip。未复制真实80MB树、执行编译器/RTL或生产run/main；实际源树只读后验单独列示。SOURCE及精确命令总审身份见STATUS，原41冻结成员不热改。

本批公开16份安全原件、STATUS与本计划完整后继。私有绑定/profile/COMMAND/outer/现物路径/日志仅本地。full job/full block=false，历史Host故障重现、official/application accuracy和typed-to-RTL仍null；唯一实际仍由父在源/命令独审与当前准入后执行。


## TEMP 2026-10-19 23:48 UTC：Owner cache 编译成功，有限 typed-RAM 运行失败

原 session 44110 已结束：build 自然 0 / 62.420557 秒，run 自然 1 / 109.877769 秒；两阶段 cleanup=true、timed_out=false。outer=1 / 176.78127549499914 秒。原 EXECUTION_RESULT 为 INCOMPLETE、ValueError，原安全码/边界为 null；run 监督诊断保留 CHILD_EXIT_NONZERO。本轮实际总体为 FAIL，不篡改原收据。

cache 续接复用原固定生成源码，未重生成或重 backend。新的 owner ELF 为 12718080 B / a91ff84921ba6b116b762a3f4eb384f1518be88e3feca562c1ee2996b6ba4fa1；原 516 个 obj 源及 makefile 字节/旧 fixture 读取合同不变。960 秒总额、600 compile + 300 run + 60 落证、单 CPU、AS 6 GiB 与原 8 GiB/3 GiB 准入均保留。

run 末行 edge=76580、CONTRACT_FAILURE / RESET_REQUIRED_HIGH，采样为 HIGH_EVAL_POST_SOFTWARE_PREVIOUS_EDGE。软件已记录两 window terminal（52379、62000），首 drain request=1、terminal=0；matrix groups/dones=2、issues=7680，当前 RTL wideSteps=7680/steps=61440/mask255。软件写账本为 descriptor1、beats10、committed640、response0；N0/Wq returned bytes 为 786432/491520。软件只处理到上一沿，response0 不能推断当前高沿未 ACK；typed-RAM 账本也不是 AXI B 退休证据。

owner_sharedPoison/router_bad/coor_bad/coor_serviceError/win_resetRequired 同时观测为 1；不认定其首因次序。typed RAM 或 RTL 原因待查。本轮并未执行 Host PC0 前缀或 iDMA/AXI，ng160 partial1 首 issue 目标未达，不能与原 Host 同因合并。完整 job/block 未完成、五 block 仍 0/5，official/application/typed-to-RTL 三资格及 historical_host_failure_reproduced 均保留 null。

安全详情位于 candidates/host93_first_n0_sources/owner_micro_cache_failure_actual/ 的 SUMMARY.json 与 README_CN.md。原证据 MANIFEST 959 B / 140559eb53a4ef330a5e8e54b1b544d801b323bc2c39bcfe2b9bb3cb969935f4；原日志/工作树/数组/二进制私有保留，本批无任何新 native 或测试。

正式 actual 独审已封：review_owner_cache_actual_20261019T2348，M786/0a832dcb156af5f8df8620b2b43846dd0071bd36afdf42c0b9e3091a7fafbdcd，S9476/14bb3cbebaa5002dad596c235db675cec66904a60e0ec8c8101d735ac853f1b1，verdict ACCEPT_ACTUAL_OWNER_CACHE_BUILD_NATURAL_ZERO_RUNTIME_RESET_REQUIRED_HIGH_ONLY；仅接受上述有限事实，根因与 Host 同因仍未知。v2 为 metadata-only 后继，事实和范围不改。本段为原 279840 字节计划的纯追加；发布使用完整 replacement，不把完整文件再次 append。

### Owner 响应退休观察调度 v3（独立 SOURCE 后继，2026-10-19）

本批在独立 owner_micro_sampling_v3 目录保存原 owner driver 的最小观察调度后继；原 v2 与 session44110 FAIL 不改。当前只有 SOURCE/纯冷测，v3 编译/native/RTL 均 NOT_EXECUTED。

固定原 Dense 合同只以响应 fire、tag 与 error 判 ACK，有效零 data 与真实 adapter 相同。首 good ACK 使 Wait→Req 并累加640字节，而外部 C++ 响应 valid 尚未更新时，raw-high 的 unexpectedAck 组合门可能立即变1。原实际记录只观测到当前 RTL 字节640/writeDebt0和上一沿软件response0；缺少该沿 writeState/rawAck/drainPoison 的直接值。静态源码与原生成调度支持这种半步观察解释，但不把纯表达式反例冒充新 RTL，也不判定与原 Host ng160 同因。合法 valid 保持到下一低沿并非采样协议违规；持续越过下一高沿的重复响应仍应拒绝。

唯一生产变化在 main 调度及同记录诊断：原低沿门、采样 fires、Ram/Progress 退休校验正文完全保留。原高沿95字段和reset值保存为 raw_high_before_settle，runtime fatal仍立即拒绝；随后按原采样事务结算一次，在 clock=0 驱动已更新 producer，eval/priority/eval 完整 settle 后检查完整 reset/runtime，检查先于任何下一上升沿。新 LOW_POST_EDGE_SETTLED_SOFTWARE_RETIRED 软件账本含当前沿；原高后快照另有明确样本标签。没有写内部状态、清错误或mask门。

每轮低沿前2次eval、高沿1次、falling-low2次，timeInc仍2次；原下轮开头的同一次下降沿提前到本轮末尾，不增加 owner/Matrix 上升沿。下降沿可以正常触发原wrapper的seq-DPI更新，不能称从不调用seq；原seqnum选择保持不变。目标停止点现在包含末尾正常下降沿，仍无下一计算上升沿。

六件其余生产原件逐byte不变，固定输入、196端口、95观察、VLT、500000周期、12801目标与原退休/数值资格门不变。公开冷测93主+8loader，普通/-O/搬迁四模式全部通过，涵盖bad tag/error、持续reset/poison、stall、重复响应、原事务错误、一次退休无double/missed及raw快照保留。这些不执行C++或RTL。正式 SOURCE 已获有限 GO：review_owner_micro_core_v3_20261019T2356，MANIFEST 1181 B / 6b109cd2f3b65e6f0b57327966f595f4703edf9b5c05f8518d27c58a7a8430ec；SUMMARY.md 4658 B / 947fb90d4aeae27c3b727efab7ea4b2784a0b367201a5453363da2af8e7aecf3；verdict GO_OWNER_MICRO_V3_FALLING_LOW_SETTLE_SOURCE_ONLY。独立核28成员/17来源、93+93冷测及26+26原式诊断；只授本片SOURCE，原actual缺叶的局限仍保留。

后继caller按另审540秒共享上限准备driver-only编译120、链接60、运行300、落证60，单CPU、AS6GiB；复用原owner archive/runtime须独立资格，不能从源码推定本轮已编译或修复成功。official/application/typed-to-RTL、历史Host故障复现均null，full_job/full_block=false，五block0/5。

本批公开原生产/可搬迁cold与安全说明及本计划完整replacement；私有生成坐标报告、原日志、数组与binary不入公开。仅源码发布，不触发新的Host/RTL/native作业；workflow文件不变，普通push轻量guard另记。


## TEMP 2026-10-20 00:05 UTC：Owner v3 driver-only 540 秒续接 SOURCE

原 owner cache actual 的 build 已自然0，但 run 在 RESET_REQUIRED_HIGH 自然1结束；这份失败及上游原因未明均保留。本片只准备复用已审 owner model 的普通 archive +3 runtime objects，fresh 编译新的 v3 driver.o，再 direct g++ link，随后一次有限 owner 局部 run。无 make、generation、model C++/PCH/child library 或 backend 重编，旧 driver.o 和旧 executable 不作为新驱动输入。

精确复用12件，共24151608 B：2 generated headers、6 Verilator headers、3 runtime objects、1 VQwenOwnerKernel__ALL.a。top普通archive已含23对象成员，其中10个child对象；无需另链child archive。原608项树（599files、493245462 B）、成功build log/.d/makefile、receipt及formal review前后只读核验，原generation/source/profile/dependency门保留。所有编译输入复制到fresh路径并同buffer验后写；新.d恰核12个依赖及顺序，不借旧fixture绝对路径。新ELF及固定needed库在link后/run前后重验。

v3 production manifest1019/67ae76c51aacbcabb47bdf10cc59a8d1cb7c506760907d506c7f09681279b6fc；仅driver变化，6件原接口/观察/辅助同字节。原196端口/95字段与固定header reader不变。主caller由已审cache main的29处精确替换派生并可逆还原；原ci_support_v3监督、39系统依赖与只读mount profile不改。

唯一总540秒从父outer最早t0计入全部加载/hash/staging；compile120 + link60 + run300 + tail60，各native工作/CPU105、45、285秒，原15秒监督余量保留。阶段前及preflight后要求完整当前窗口加尾限；不足即INCOMPLETE。单CPU/AS6GiB、原MemAvailable≥8GiB和盘≥3GiB每阶段准入。普通Python -I -S -B父入口：530TERM+5KILL+5落证，不使用-O，不重置起点。

作者helper-boundary purecold39项×普通/-O/搬迁普通/搬迁-O=156 PASS，0fail/error/skip，最高RSS26256KiB；不是完整run mock，也没有native/编译/RTL。另独立只读原现物回放通过608项树、12项输入、95声明及旧.d的明确路径投影；该投影不是新编译器实际.d。源码M6623/80ce83fbac42216017ab65691c9cacc95d6102ceae52e65c633f9ac0e5e2e39e，COLD1996/b855eefe490313ece8fdea755dde5efa3c88b290ef2bc63ace6725e6fbbfb5a5。

SOURCE 正式独审：review_owner_driver_relink_source_20261020T0003，M2388/64e722506ec2e4fcbf57b8619f3f261c8927b4475d0d7d75434c7a15c7d6fd3c，S5238/a092a51a7d94f0cc2eee1f65e4b909cc5bea8ec40797a9c66e3c305c614420dd，GO_OWNER_DRIVER_RELINK_RUN_SOURCE_AND_EXACT_540_COMMAND_ONLY。独立39+39 helper-boundary冷测通过，与作者156分列；12复用/39依赖子审已闭，未重执行原actual。本片实际NOT_EXECUTED；300秒与500000局部cycles不保证目标完成。完整bounded JSONL原样保留供后续actual独审，caller不解析raw_high_before_settle并授资格。full_job/full_block=false，official/application/typed-to-RTL及historical_host_failure_reproduced均null，不把局部owner与原Host认定同因。

公开前缀 candidates/host93_first_n0_sources/owner_driver_relink_run/；只投影14件安全public原件+STATUS和完整计划。私有binding/COMMAND/outer/原.d夹具、原工作树、数组、日志不发布。本段是原285715字节计划纯追加，实际发布用完整replacement，禁止把全文件重复append。


## TEMP：Owner v3 driver-only 真实 settled failure（2026-10-20）

唯一 session 92317 已自然终态：compile 0 / 1.663322s，link 0 / 0.123427s，局部 run 1 / 150.140876s；三阶段均未超时且 cleanup=true。outer exit=1，159.6861525139975s，于 2026-10-20T00:12:16.633883+00:00 结束。原 EXECUTION_RESULT 保留 INCOMPLETE/ValueError 和 null failure_code/boundary；run 原诊断为 NATIVE_SUPERVISION/CHILD_EXIT_NONZERO，安全实际结论为 FAIL。

本轮只新编译 v3 driver 并链接已核 owner archive/runtime objects，没有复用旧 driver object、重生成或重建 backend。新 ELF 12726288 B / 211b05da7c5747970277f2d0756ea25a39f6156113a3c1bf803796f57cd2ab4e；完整四行运行日志 20870 B / 4eacd6c718e0c7f69a440889a9d03345fbce45e13b30ef3028a8aaabbdca7ea1。

末 edge=92364，RESET_REQUIRED_SETTLED；同沿 raw-high 和完成软件退休后的 low-settled 均 resetRequired=1，dense_state=6/status=8。固定 Protocol.scala 3123 B / 5c94def481dede0195f989608c1827ded32f2d83c752617945695f7d82f64783 定义 Numerical=8、Memory=3，故本次属于 Numerical 状态类别，具体首写分支及上游原因仍 UNKNOWN。

本轮首 drain 已真实退休：128 个 typed write responses、128 descriptors、1280 data beats、81920 committed bytes，drain terminal edge=81467；这不是 Host AXI B 证明。第三 window request edge=81469，ng=160/K[0,1024)/reuseA=1；末条 requests=3、terminals=2，matrix groups=3/dones=2，wideSteps=12800、steps=102400，N0/Wq returned=786432/819200B。无第三 window terminal，也未达到 ng=160 partial1 首 issue 目标。末条 valid=0 的元数据不作为本沿新握手或 terminal。原 Host 同一计数/窗口位置仅相容，同因尚未建立；旧 v2 早期 FAIL 和全部原证据保留。

正式 actual 审：review_owner_driver_relink_actual_20261020T0014，MANIFEST.json 770 B / 1e829f2d6553cc0f1b6fe0223851325767e8c7af5de934154ef554eafe0a8be2；SUMMARY.md 8002 B / 05bc84539e07589dbb3f216de953d32e64b9ed3f29b0161485be07eb51292953。verdict ACCEPT_ACTUAL_OWNER_V3_RELINK_NATURAL_ZERO_SETTLED_NUMERICAL_STATUS_FAILURE_ONLY。独立核当前 53 项树、七证据、42 caller/28 core、338 原生成输入、完整输入及新 ELF/.d/archive 关联；39 系统依赖沿 SOURCE 资格，本次未重 hash。独立终态读验不倒填运行失败后未执行的 success-only postflight。

公开安全两正文位于 candidates/host93_first_n0_sources/owner_driver_settled_failure_actual/；不含机器私有路径、原始日志、数组或二进制。证据 manifest 957 B / ebfd84179a8b3dd6ee270977a5959bc16aebc1d83c521a562afb2f65276c54cf。该摘要没有新 native/RTL/测试。Host 前缀和 iDMA/AXI 未执行，完整 job/full block=false，五 block 0/5；official/application/typed-to-RTL/historical-host-reproduction 均保持 null。下一步须单独定位 Numerical 首写，不把本次 FAIL 改记为成功。


## 2026-10-20：owner Numerical 首坏只读闭包 v4 SOURCE（正式独审通过）

本批只发布独立源码候选、可搬迁纯冷测与安全元数据；不触发新的 Host/RTL/native 作业。workflow文件不变，普通push的轻量guard另记。原v3及原92317实际失败证据不改，首写数据和上游根因仍未知。

- 独立目录：`candidates/host93_first_n0_sources/owner_micro_numerical_v4/`。生产仍原7件，仅 `owner_micro.cpp` 改；另6件逐byte同v3，原196端口、95控制观察、VLT不变。完整源码逆投影回v3逐byte成立。
- 新Numerical闭包明确独立于旧95控制字段：69个标量、4096个Matrix结果消费alias、16个tile响应值、6个burst端口，共4187当前固定root声明叶。消费矩阵、宽度、生成producer和driverconsumer随源码固定；已有root包含全部字段，无VLT改动/重生成。
- 原LOW_PRE_EDGE实际fire时只读保存三条Numerical入口：结果协议元数据+完整有限性掩码/BF16范围、burst源格式/RNE有限性、active drain响应error和真实selectedTile key。4096结果只在实际fire扫描，保完整样本SHA、计数与首坏坐标/raw32/指数类别；不输出payload数组/权重。
- 保旧status与high/settled实际status、三候选集合和首次0→8的低沿样本；后写Protocol/Memory/admission/reset未全部采样，same-edge winner明确UNKNOWN。辅助观察错误不替代原失败/exit。原Ram/Progress、驱动信号、握手、有限门、每轮5eval/2timeInc均保留；不是修复RTL。
- 四模式同buffer冷测（原/搬迁×普通/-O）每模式138主例+8loader例通过；仅纯mock/source，没有执行C++/RTL。含全4096alias顺序、首中末坏值、NaN/Inf/次正规、M16掩码反例、BF16范围、无fire、优先级、首坏保持与有界输出。
- 当前固定N0/Wq、M128、K[0,1024)+[1024,1536)及局部目标不变。未来仅沿原caller复用archive/runtime，540秒compile120/link60/run300/tail60，单CPU、AS6GiB；本冻结阶段actual=NOT_EXECUTED。
- 静态计划已独审：`review_owner_numerical_firstwrite_plan_20261020T0022`，M411/5d1fc6521d62f2b9df0fdbb133406c66340e4fcf7e165f1eef39bdcdc0bb5220，S4460/38ed35b8cc048613ad27895bd4519b4ee789557b33c9736dd93cfbc77b138c93。v4生产SOURCE已封 `review_owner_micro_core_v4_20261020T0031`，M2326/0a21394bd641a78cd6e07831873e199669f81bd9c2068115abab04db97f58984，SUMMARY.md4320/1eee1058e4e64039525f9364b9ea8ed5e158843612b0f32e36057d83c096d50a，结论 GO_OWNER_MICRO_V4_NUMERICAL_CONSUMPTION_OBSERVER_SOURCE_ONLY；独立搬迁普通/-O 138+138 主例与 8+8 loader 例通过。只补 metadata，生产与 COLD 不改。
- 正确算法数值范围不等于本轮RTL数据正确；旧Host仅位置相容，不能倒填同因。official_raw/application_accuracy/typed_recipe_to_rtl均不授PASS，full_block=false。


## TEMP：Owner v4 Numerical 只读闭包的原540秒 pin-only 接线（2026-10-20）

在已发布并独审的 v4 owner driver 之上，本批只更新既有 driver-only caller 的 CONFIG_PIN、DRIVER_PIN 与 entry CALLER_PIN。run_owner_relink.py 为31361 B / 134a817c0dfae21736654e7bfaa40d4ff870e2de552366353c741f9512a6741b，launch.py 为2052 B / ca116a5164013bbbae45b44c33c62a4e16e6884b51a58d2ccda0bc18855396b7；四个 reuse/supervision/cache/header helper 及全部函数字节不变。有限逆投影恢复原 caller/entry；原监督、命令、依赖规则和首错门未放宽。

固定 v4 production manifest1020 B / 50ceabdd66b261e14084c2efe0609601b63d2724293ccd7a6f47531d6baebde0，7件中只 owner_micro.cpp 变。4187叶 Numerical 资格由 review_owner_micro_core_v4_20261020T0031 绑定实际 producer 与固定4630258B root header：M2326/0a21394bd641a78cd6e07831873e199669f81bd9c2068115abab04db97f58984，S4320/1eee1058e4e64039525f9364b9ea8ed5e158843612b0f32e36057d83c096d50a。原196端口/95观察不变，不能用旧95门冒充全部新增数值闭包。

精确复用仍是原12个已核 owner header/archive/runtime 输入，共24151608B；不复用旧 driver object，不调用 make/Verilator，不重新生成、backend或model编译。fresh 新driver编译→链接→局部run；新.d恰12有序fresh user inputs，原件/副本/对象/ELF和完整输入按原门前后核验。原540总墙含检查及复制，compile120+link60+run300+tail60；各native CPU105/45/285，单CPU、AS6GiB，MemAvailable≥8GiB、盘≥3GiB。父普通-I-S-B，最早t0/530TERM+5KILL+5落证不变，完整阶段窗口不足即INCOMPLETE。

本次作者增量16×4=64 PASS；独立16+16=32 PASS，分列不合并。旧39×4与只读库存回放只继承未重跑；无本次数值或RTL实测。总SOURCE review_owner_driver_relink_v2_source_20261020T0034：M1116/33ec0c74734089ec7b960b3cb0cc4f2e13a4946361957e56fad737d5927a4d17，S3301/915a66f448c617f149e0a277969eb3f96b5c86c19abd6179a592b1d38d319707；verdict GO_OWNER_NUMERICAL_DRIVER_PIN_ONLY_SOURCE_AND_EXACT_540_COMMAND。总候选M9701/cc119fafceffd703688e78fdb3cdda627193a763e55e42afc2fce8dad406d221。

公开15原件+STATUS位于 candidates/host93_first_n0_sources/owner_numerical_relink_run/；私有绑定/COMMAND/outer、测试机器路径、日志、数组和二进制不公开。当前该后继实际NOT_EXECUTED，额外扫描耗时未知，300秒不保证目标到达。caller保完整bounded JSONL，不靠候选集合或status布尔授PASS；具体首写/同沿winner/Host同因需实际充分证据，旧92317 settled Numerical FAIL及早期FAIL原件保留。完整job/fullblock=false，五block仍0/5，official/application/typed-to-RTL/historical-host-reproduction均null。


## TEMP：Owner v4 已消费的 Matrix 非有限结果失败（2026-10-20）

唯一 session1021 已自然终态：compile0/1.782645s、link0/0.123377s、run1/154.618345s，三阶段无timeout且cleanup=true；outer1/164.20999363900046s，于2026-10-20T00:45:12.880209+00:00结束。原EXECUTION_RESULT保留INCOMPLETE/ValueError和null failure_code/boundary；原run诊断NATIVE_SUPERVISION/CHILD_EXIT_NONZERO，实际结论仍FAIL。

末edge92364的LOW_PRE_EDGE_ACTUAL_CONSUMPTION记录真实result valid/ready/fire均1、context0/error0/last1、result_protocol_bad=0。4096个未屏蔽FP32槽中1472非有限、2624有限，masked=0/BF16 range rejects=0。首坏index0/raw0x7fc00000可判QNAN，logical row0、ng160+offset0=输出列160；没有逐项分类其余1471非有限，不能全部写成QNAN。payload little-endian SHA为853e86559d6b797538ab01a4a754fda33423c26f48c2364312f287d3e6c31ddd。整组计数/hash来自已审fixed scanner的实际消费日志；数组未保存或公开，独审未重算4096项。

消费前finite0/responseBad1/status0，result finite disagreement0；候选Numerical写matrix1/burst0/drain0，本沿burst/tile fire均0。同沿high status8、falling-low settled仍8，末RESET_REQUIRED_SETTLED；原same_edge_winner保留UNKNOWN_NOT_ALL_LATER_WRITES_SAMPLED。记录闭合实际消费与非有限谓词及状态转变，非有限值上游来源、所有后写优先次序仍未知。groupSequence3、ng160/K[0,1024)、pendingK1023/pendingContext4，wide12800/slice102400；pendingContext不是当前消费result context。Host仅位置相容、同因未证。

先前首drain在edge81467已退休128 typed write responses/81920 committed bytes；第三window request81469，末3requests/2terminals、3Matrix groups/2dones；无第三window terminal，也未达到ng160 partial1首issue目标。本轮仍是owner typed-RAM场景，未执行Host PC0前缀或iDMA/AXI。原v2早期失败与v3 settled失败保留。

正式actual review_owner_numerical_actual_20261020T0046：M1213/e569e7897d10f300c245b24cc9ffeb72d8cc7dd95282ae69835b558c32ac4685，SUMMARY.md9536/01e92b6d94c23679c80efc7c70ebae1b0e03ab9c3c1336fa70a1f80c74737158；ACCEPT_ACTUAL_OWNER_V4_MATRIX_NONFINITE_CONSUMPTION_FAILURE_ONLY。独核53项当前树、338原source、7fixture/12copies、完整输入及ELF/.d/23archive/3runtime；39系统依赖及原608整树未本次重hash，success-only caller postflight未执行，独立读验不倒填。

七证据manifest957/6912c2979ad9c37a89ef334e88af8eefb2718cef9ee48e23257bcbfd5c8c9a26，完整四行run log34777/5bf4b4fa15b820c25f2743777286c2fb823fdee2ca910975f8f5831974a57260，新ELF12826184/482a6d48bf8e3e320c9dd4634308dad1209acc9d49ad6c44afdd8f81eaacfceb。公开安全摘要在candidates/host93_first_n0_sources/owner_numerical_failure_actual/；不上传原权重、数组、完整日志、二进制或机器路径，摘要无新native/测试。fulljob/fullblock=false、五block0/5，official/application/typed-to-RTL/historical-host-reproduction均null；后续只可依据新证据定位上游非有限来源，不能将本FAIL改记PASS。

## PASS（有限范围）/ TEMP：离线证据容器校验器（2026-10-21）

- DONE / PASS：新增 `candidates/fixed93_offline_evidence/` 的只读校验器、纯合成测试及 pinned r3 decoder。复制至本工作树后重跑 16 个 unittest 方法通过，0.416 秒、最大 RSS 21592 KiB。未运行 DUT、native 数值内核、Chisel elaboration 或 RTL。
- 精确范围：外部可信原会话终态声明与 receipts 的一致性、双 LEC1 流完整文件身份、frame/hash chain、真实 EOF/FINISH 和外部 seal；缺终态、身份混淆、清理异常、截断和尾随字节拒绝。原会话 attestation 必须由可信原始终态证据建立，本工具不生成该证据。
- ONGOING / TEMP：算法数组、token/operand 语义、调度/cache 对应、数值与完整 block 尚未由本工具验证。成功输出强制保留 fullblock_acceptance=false、numerical_acceptance=false、RTL=false；不得将本批合成单测升级为 M128 通过。
- TODO：增加有界语义层和独立数值审查。已有失联运行仍缺可信终态与清理证据，不读取未封流造 PASS，不重复昂贵作业；此局部阻塞不应阻止独立代码和合成测试继续。
- 五 block 完整 RTL 仍 0/5，无新增 MAC 利用率实测。未上传权重、可重建 tensor、真实日志或二进制。本批不删除临时数据。

## TEMP：Fixed93 PV16 归一化原位复用核心补丁（2026-10-21）

- DONE / PASS（有限）：`candidates/fixed93_pv_normalization_reuse/` 保存两文件核心 patch、输入/输出 pins、便携合成测试及编译复现脚本。入本工作树后 root 再跑 20 项测试通过（9.425 秒）。真实 Python owner/shared clients 只跑 synthetic M1/M2/M16；算术服务是 exact-rational RNE 替身，不是 native、Chisel 或完整 block 通过。
- 核心改动：每 head/query 的 col=0 计算归一化 FP32 并覆盖原 probs，后 7 个 PV16 列组复用；Scala 原 exp 写入和新写回合并为一个 write site，不新增缓存容量/FMA/寄存器声明。仅选中 packed-QK16 profile 生效。物理端口与面积未经 RTL/综合签核，Scalar 调度明确改变。
- DONE / PASS（有限编译）：修改后的单个 Qwen2Block.scala 增量 scalac 通过，19.63 秒、16 classes；没有 elaboration、CHIRRTL/SV/RTL 或仿真。便携 compile wrapper 本身未再运行，真实同源编译摘要单列，不重复计数。
- 性能仅预测：M128 少 693504 次归一化 Mul，源码无停顿状态模型少 2774016 拍；非 RTL 实测，DDR 事务与 Matrix issues 不变。当前选中调度中 Attention 1609728 笔读写各至少占两个与新 Matrix step 不重叠的握手拍，完整 block T>=5529600；固定4096 MAC/拍、有效MAC6014828544，保守源码上界<=26.5564236111%。允许在飞流水活动重叠，不能据此称上游整体不支持高利用率。旧63.5659%是忽略此供数约束的 issue-only 上界，不是实际可达预测。
- ONGOING / TEMP：observer 新schema、最新33-symbol helper基线合并、closure/预算/admission独立集成。本核心包不含 observer，不可直接接旧 observer，也未准入完整 M128。
- TODO：先完成新观察契约的有界集成验证，再解除 Attention 串行供数瓶颈。完整五block RTL仍0/5，80%/90%目标未达；不上传权重、可重建tensor、原始日志、class或基线副本。

## PASS（有限）/ TEMP：PV 复用 v2 独立容器读取器（2026-10-21）

- DONE / PASS：新增 `candidates/fixed93_pv_reuse_evidence/`，保留旧 v1 读取器不覆盖。入工作树重跑21项合成测试通过（1.157秒、21892KiB）；独审另写16项微型端到端案例通过，两者不合并冒充实际模型覆盖。
- 新入口严格绑定归一化复用的 plan/observation/contract 与 ordinary event-v2，exp仍为原v1；拒绝旧v1混配、1/8/7声明错误、bool冒整数、缺终态/FINISH和尾随字节。只验证可信终态声明与容器，不证明真实693504次复用、数值或调度语义。
- ONGOING / TEMP：source closure/anchors/preflight接线；预算增量经有限SOURCE审查为+99072事件、+24470784字节，不授实际运行资格。
- 完整block/native/RTL均未执行，本批不继承前任候选的实际PASS，五block RTL仍0/5。

## PASS（有限）/ TEMP：PV 复用源码接线准备（2026-10-21）

- DONE / PASS（有限）：新增 `candidates/fixed93_pv_reuse_integration/` 的小源码 overlay、便携元数据生成器、relative pins、预算提案与纯源/MOCK检查；入工作树后13组通过（1.374秒、23468KiB）。没有复制完整源码树或权重，没有真实preflight/native/DUT/RTL执行。
- 321项身份清单只允许 owner 与 selected Qwen2Block 两项变化，其他319项变动拒绝；更新两处owner anchors、1/8/7合同及算法seal的证据清单传播。observer以当前严格33-symbol helper基线合并，未带回旧_FuncPtr启动错误；保留旧冻结候选和原失败证据。
- 预算提案独审：净增99072条事件，raw增加3071232字节，frame/metadata增加21399552字节，合计24470784字节；owned上界22917099404字节，含原reserve的startup门23453970316字节。预算仍OPEN，不能凭source审查授实际运行资格。
- ONGOING / TEMP：新完整assembly/preflight、实际constructor/dispatcher、资源准入和模型完整128token数值验证。MOCK字段检查不等于完整closure内容重hash，也不等于新模型运行通过。
- 新源码准备不继承前任actual PASS，完整五block RTL仍0/5；最终完整RTL数值和90%利用率目标继续保留。

## PASS（有限）/ TEMP：外部冻结输入只读接线（2026-10-21）

- DONE / PASS（有限）：新增 `candidates/fixed93_external_frozen_layout/`，固定逻辑文件身份映射到两个显式冻结外根，允许新候选复用原数据而不复制权重。入工作树重跑14组 resolver 合成测试（0.038秒）与5组 CodeType/synthetic 路由测试（0.057秒）通过；独审另有16个resolver案例与41个原seal谓词正反例，分列不合并覆盖。
- 同一FD读取并hash、前后身份检查，拒绝路径逃逸/别名/写入/祖先变更；默认reference只stat，payload仍须原postseal开闸。Python audit guard不是native或OS隔离，不宣称覆盖任意native系统调用或预先持有的可写FD。
- 新loader仅编译已pin源字节，不用未pin pyc；before/after检查保留code/globals/class/defaults身份。原21/17/1、finalfence、debt和same-live门未弱化。
- ONGOING / TEMP：真实小assembly及完整preflight。文档process cap指preflight-only/no-DUT，不存在SOURCE_ONLY绕过：真实预检仍须321源码、全部prep、1638 runtime和46冻结文件全hash（后者189998063字节），30份reference仅stat。预计读取约851MB，但本批未读取真实冻结数据，也未实际预检/native/M128/RTL。
- 旧失联运行及唯一证据不动，未删除临时数据；完整运行容量门不下调，五block RTL仍0/5。

## PASS（有限组装）/ FAIL（实际预检）：固定Git依赖与工作树解耦待修（2026-10-21）

- DONE / PASS（仅组装）：保存 `candidates/fixed93_external_assembly/` 的小型builder、pins与脱敏摘要；实际唯一组装1.720秒自然退出0，547文件/8806882字节，无输入/参考读取或复制，无DUT/native。摘要记录组装时点，不是后续预检结果。
- FAIL：另行实际执行完整preflight，1.018秒自然退出1、未超时，runtime校验发现活跃工作仓库 `.git/HEAD` 与旧pin不同，未到46冻结输入hash。因此不能宣称约851MB全部验证，更不是模型数值失败或通过。原失败组装和记录保留。
- 归因：Git确为执行依赖；原配方执行 `git show HEAD:<source>` / `rev-parse HEAD`，admission安装并校验固定Git profile，不能删掉HEAD检查或盲改pin。错误耦合在于使用会随本地提交变化的publication工作树来承担固定算术源码来源。
- ONGOING / TEMP：将固定detached commit及exact pack/profile迁移为独立可恢复源码依赖；不回退工作树，不改失败候选，不弱化原固定源码/对象校验。新候选须重新真实preflight，不继承旧PASS。
- 完整block/native/RTL未执行，五block RTL仍0/5。builder源码入本工作树仅逐pin核对和语法检查，没有重复组装。

## PASS（有限实际预检）/ TEMP：独立固定Git执行依赖（2026-10-21）

- DONE：`candidates/fixed93_git_runtime_isolation/` 保存两个便携builder、两组synthetic测试、AST fixture和相对pins/摘要；不提交Git对象、真实runtime清单或原始日志。入工作树重跑30项snapshot测试（1.285秒）与29项successor纯元数据测试（0.666秒）通过。
- 实际固定快照唯一创建自然0/0.266秒，20文件/63240510字节；原固定HEAD从已pin字节重建，5个其余Git文件按原pin复制；只迁移6Git+12profile路径，其余1620 runtime pins不变，15份非生成Git/profile内容不变。没有执行Git命令、profile.verify或native数值内核。
- 实际后继组装唯一创建自然0/1.572秒，548文件/8815291字节；原321源码逐字保持，只更新runtime/top/prod及增加隔离说明。原0150失败版本不动，不回退publication工作树。
- PASS（仅真实SOURCE preflight）：新候选manifest cc82716a4801c111225c1dc6cb4435ca3120482f4e21ebd01fd1d3a6f1e7b90b，完整preflight自然退出0/1.519秒、RSS22828KiB；1638运行依赖全hash、46外部非reference文件全hash、30 reference仅stat。此范围基于已pin源码控制流及真实自然成功，不宣称独立syscall轨迹证明。
- ONGOING / TEMP：真实runtime初始化/构造、完整模型M128、调度/数值与RTL仍未通过；预算OPEN、actual_admission=false，完整run空间门不降低。五block RTL仍0/5，90%利用率目标保留，不能把这次预检通过当推理通过。

## PASS（有限实际startup）/ TEMP：PV复用初始化和空observer生命周期（2026-10-21）

- DONE：新增 `candidates/fixed93_pv_reuse_startup_probe/` 的便携源码、relative pins、AST checker及安全摘要，无ADMISSION、原始routes/logs/数组。入树checker仅bytes/14个Python AST通过（0.054秒），不重复实际运行或继承内部38项cold结果。
- 新候选唯一cold含完整preflight和24监督mock，自然0/1.519秒；随后root独立单次准入45秒总窗（30工作+5清理+10post）、1CPU/2GiB、16MiB owned。实际startup自然0/18.2306秒，没有外层soft/hard停线。
- PASS精确范围：实际当前构造、原已核ELF加载/reset/FENV等初始化、固定Git profile验证、空Attention observer ctor/enter/exit/save；两次边界均在首个advance之前，pc0/decode、模型jobs/requests/completions/producers/服务事务及22区域写ACK为0，reference payload reads为空。不是zero-native，也不是模型数值验收。
- 独审核1011实际observer open routes/327 distinct，9个witness各3次、manifest3次；实际empty记录/raw均0，summary保留INCOMPLETE、reuse0、both_domains_verified=false。52字节未封wholeblock头未当完成证据。
- 身份/资源：228pins、lease/CONSUMED/原进程start ticks、WNOWAIT自然0、reaped/group absent/cleanup confirmed闭合；whole CPU18.1445秒，采样组RSS242839552B，独立最终15文件552322B。LAUNCH的550900B为最终receipt写入前快照，不冒充最终stat。
- 独审实际摘要SHA69ef9b3f2955cba917dab9db71a3bf0f6883ba55c81adba56d66d9686f3592dc。该资格不授新fullblock运行，不复用一次性authority，完整M128/数值/RTL仍未通过，五block RTL仍0/5。

## PASS（有限SOURCE/cold）/ TEMP：恢复完整M128入口与精确容量预算（2026-10-21）

- DONE：新增 `candidates/fixed93_pv_reuse_fullblock_return/`，仅10份便携源码、相对pins、摘要和checker；不是完整可执行组装包，不含机器专用预算/ADMISSION、输入、参考、原始日志或二进制。入树后bytes/5 Python AST checker自然0（0.017823秒、RSS16000KiB），未执行生产模块。
- PASS（精确范围）：新完整候选唯一组装550文件/8827685B，1.418925秒自然0；原306源码、9 selected、6 support逐字不变。恢复原完整runner的3次advance、producer→KV→Attention→tail→双封流→postseal oracle，未继承startup-only停线。三处loader从已核raw source编译，避免未pin的pyc；没有改算术源码。
- 唯一SOURCE/cold含真实preflight与24监督mock，自然0/2.371522秒；manifest 4e5496a21b3ecd2b99c0022c1e99bb1666eafb284c84e91b525fc0e1c89c2889，budget 571cbb74b8bbc88aecabb52c493f7795441eef4d07eb4d6eafd7986ab5228617。独审仅GO_FIXED93_M128_FULLBLOCK_SOURCE_COLD，actual未授权/未执行。
- 精确字段上界审计使Attention容量预算减少813159528B；记录数量/内容、wholeblock上界和536870912B余量均不减少。future-owned22103939876B，fresh可用空间要求22640810788B；它是现场检查而非排他预留。
- ONGOING / TEMP：实际准入前另发现observer逐次身份检查反复构造ABI表/profile副本的时间风险，正在做无模型微基准和保持逐次核验的窄优化。本候选冻结，不因SOURCE/cold GO直接重复昂贵前缀；6600秒窗口内完成尚无证据。
- 完整M128数值/实际RTL仍未通过，五block RTL仍0/5，未新增利用率实测。本批不删除任何临时数据，不继承旧失联运行PASS。

## PASS（合成差分）/ TEMP：观测器无证据回调热路径（2026-10-21）

- DONE：`candidates/fixed93_observer_op_boundary/` 保存原位小patch、完整observer源码、relative pins、显式policy及合成测试，共11文件。只在 `_trace` 原try内新增一条早筛If；移除此If即恢复原0300模块AST，原identity、dispatcher、另一个observer、16字段/line/exp/fence逻辑不变。
- 新policy为 `op-evidence-boundary-v1`：只对exact `_op`、caller非exact `_attention`的正常call/return保留code/thread/owner轻量核验、跳过全ABI/profile库存核验；exception与其余事件仍走原路径。明确不同于旧逐回调防篡改契约：被滤两点间篡改并恢复ABI/profile不保证发现；持续漂移下一保留边界仍拒绝，双故障时报告优先级可能不同。
- PASS有限范围：入树后root重跑合成测试自然0/0.167948秒/RSS22236KiB。真实共享dispatcher和原wholeblock回调用于MOCK public/support帧，六scalar消费者记录、正常/处理异常/传播异常、恢复debt、持续漂移拒绝、瞬时漂移预期差异闭合。独立listener确认_op仍被分发；不是所有域或真实中间数组的执行覆盖，无native/DUT。
- 独立无ELF的同ctypes结构微基准：active dispatcher正常call/return pair中位164.979→9.000微秒，约18.33倍；仅此回调成本，不是完整M128或硬件速度。直接callback新计时部分零增量是CPU时钟粒度，不是零成本。旧同频预构造另测仅约1.09倍，未混入本版。
- ONGOING / TEMP：新policy真实装配绑定与已有native的有限M2成功子链差分校准待做；M2不得冒充完整block/prefill通过。旧0300冻结、不借其cold或一次性authority准入新版本。完整M128数值及五block RTL仍未通过，无新MAC利用率实测。

## PASS（仅实际M2观测差分）/ INCOMPLETE：完整block仍未验收（2026-10-21）

- DONE：新增 `candidates/fixed93_m2_observer_calibration/` 20文件便携源码审阅摘录，14份原Python逐字保存；无原机器manifest/budget、ADMISSION、日志、数组、权重或ELF。入树后hash/15文件内存compile/13合成self-tests自然退出0；不执行摘录中的模型或运行入口，本公开摘录不是独立可运行包。
- 两次入口FAIL均保留：0337实际1.2025秒自然失败，原Git来源校验读mirror C++源码被新只读清单漏列；0407实际2.2029秒自然失败，缺原成功入口的3条canonical imports。两次原WNOWAIT非零退出/reaped/group absent/cleanup均闭合，未到Attention计算；0407已加载并配置模型ELF，不写成zero-native。runtime内M16命令metadata此前已生成；未到的是context的M128形状metadata/owner构造。
- 修正逐层验证：真实profile.verify核15spec/17唯一路径；0417真实加载预检R3自然0/14.240883秒，50+24描述符、9模块11类/helpers/revalidate通过。原metadata误拒和额外profile静态检查超时记录不改成PASS。预检不加载目标模型ELF、不计算。
- PASS精确范围：0417单次两个fresh进程old→new，各跑同一真实Attention M2成功子链、既有native算术与原共享dispatcher/双observer/codec。外层自然0/85.059277秒，无外部soft/hard停线；原两child WNOWAIT0及清理闭合。每arm480 normal steps，非两个M1、非完整block。
- 实际独审 `CONFIRMED_MATCHED_SUCCESS_M2_OBSERVER_EQUIVALENCE_ONLY`，摘要SHA8055216d02e43c73d62a6fefaea64f32498965421631c5028e53f9b758f5a9c4：97最终封闭文件10958996B逐hash；33数组/存在掩码/输出文件逐字相同，transport相同；每arm8565 Attention与2211 wholeblock语义记录一致。11011个opaque身份差异保留，仅允许字段，4长期对象双向映射保持；不宣称短命对象跨进程alias等价。独审未复跑DUT/decoder。
- 性能实测分层：main_loop CPU34.917529478→32.520110039秒（约减少6.9%）；wall35.905736048→33.802740322秒（约减少5.86%）。不是18.33倍整体加速，不是硬件周期或MAC利用率。合成微段倍数不能外推完整M128时限。
- ONGOING：仅主循环有界栈采样诊断设计中，尚未实际执行；已用纯stdlib实证cProfile漏trace回调内部成本，拟用SIGPROF且不改原SIGALRM期限。当前M128/fullblock/独立数值资格/RTL均false，五block完整RTL仍0/5，最终90%目标保留。不运行未经耗时校准的长作业，不清理原失败/唯一证据。

## PASS（合成）/ TEMP：每次回调缓存只读frame CodeType（2026-10-21）

- DONE：新增 `candidates/fixed93_observer_frame_code_cache/` 9文件源码/patch/relative pins/便携检查与合成测试。只将原dispatcher的6处、Attention callback的15处当前frame.f_code访问替换为该次回调内的一次读取；不跨回调缓存，不改caller的嵌套f_code或任何identity/异常/事件分支。反变换两模块AST精确还原原版；既有三个audit guards字节不变。
- PASS精确范围：入树静态checker验证全部7输入pins及逆AST；root再跑真实共享dispatcher、两个原subscriber加独立测试listener、原三个audit hook上的合成差分，自然0，wrapper1.201496秒/RSS30488KiB，无native/模型/真实M2。
- 每轮1800循环：identity两臂各3600次不变，f_code审计事件100803→23403。root三轮中位CPU227998108→95995697ns，约2.375倍；作者另一批约2.58倍，均只是合成微段，不作M128或真实M2速度承诺。只对固定已核hooks忽略的object.__getattr__事件作等效判断，不保证任意第三方有状态hook等价。
- 归因依据保留FAIL：前次真实单臂诊断自然FAIL43.2338秒、cleanup闭合，因1次重入丢样在正常退出/封流前拒绝。已关闭辅助profile有3134样本、2071栈，无overflow/深度截断，不能改成PASS；原两主流只stat未读，未导出/比较33字段。辅助报告SHA35240218ec3844f0f6bba263eba7344e595816ff08be3ba14f19ac28d9463ed7，独审仅允许不完整热点定位。
- 样本排他叶分类：audit39.247%、identity排audit后41.129%、codec2.234%；原identity45.12%是inclusive，不可相加，更不是精确CPU域测量。无需为零丢样重复诊断。
- ONGOING / TEMP：新无采样单new-arm M2接线/冷审中，拟封流后parent对照0417已封结果；历史数据不入child。尚无本补丁真实M2/M128/完整RTL资格，五blockRTL仍0/5，无新MAC利用率实测；原失败与唯一证据不清理。

## PASS（有限实际历史对照）/ TEMP：frame缓存真实M2验证（2026-10-21）

- DONE：新增 `candidates/fixed93_m2_frame_cache_validation/` 17文件源码审阅摘录，13份原Python逐字保留；不含历史HISTORY、原预算/ADMISSION、日志、payload、权重或ELF。入树静态checker核全部pins并内存compile14 Python成功，不执行原运行/测试代码；不是独立可运行包。
- 实际唯一单new臂M2无采样，自然0/37.227324秒，无外soft/hard停线。原WNOWAIT0、PID/start ticks、CONSUMED、reaped/group absent/cleanup闭合；只在新臂封流并清理后，由parent读取0417历史已封new作比较，历史数据不进入child计算。
- PASS精确范围：`MATCHED_SINGLE_M2_FRAME_CACHE_HISTORICAL_EQUIVALENCE_ONLY`，独审SHA39c51ac6aa3eff3e6778417a7f5924117f2883cb71e404c85f3074fef978bcdf；51闭合文件6019366B，33字段/presence/输出文件与transport精确相同，每臂8565 Attention/2211 wholeblock记录语义差分为空；11011 opaque差异行及4长期映射核验。未复跑DUT、未读旧未封流。
- 实际main_loop CPU32.520110039→27.504084966秒，降低15.42%；wall33.802740322→28.343136417秒，降低16.15%。这是历史单次非同期对照，不是合成2.375/2.58倍，更不是硬件利用率、M128速度预测或完整block通过。
- 原0437诊断仍FAIL，只允许关闭的辅助profile作不完整热点判断，不补造其33字段或完整封流证据。
- ONGOING / TEMP：另立tick边界完整性契约，保原full identity函数及全部数值/event/line检查，拟将完整ABI/profile值检查限定到tick边界、异常和tick外，内部每callback保cheap归属。同tick瞬变恢复检测能力变化将明示；目前仅实现/合成，不准actual。五block完整RTL仍0/5、M128未通过、无新增MAC利用率实测。本批不删除任何临时数据。

## PASS（有限合成）/ TEMP：明确tick边界完整性策略（2026-10-21）

- DONE：新增 `candidates/fixed93_tick_identity_policy/` 9文件便携源码/patch/policy/原测试与安全摘要。入树checker核外部两baseline pins、内存compile3 Python并hash通过；没有重跑原46项合成控制，也没有从此公开包启动actual。prepare-synthetic仅准备新目录并打印命令，不自动执行。
- 原full `_identity`及全部25既有方法逐字不变；同一真实owner.tick frame内部正常原保留回调用cheap thread/owner/services/library/resource/profile对象/Dense bindings key-value身份/job/client归属检查。tick call/return、异常、tick外、bootstrap、enter/exit和error后仍full；不改变14 line/6 scalar锚、所有字段/event/fence和原0325无证据_op过滤。
- 合成已独审：46scope/归属/异常/漂移控制、真实共享dispatcher双subscriber差分与六scalar40槽一致。400合成ticks的full核验8400→800；另一scalar片段46→2也仅指full核验次数，不是删标量证据。mock ABI成本约1倍，不能作真实速度判断。
- 新契约明确不等同旧逐回调防篡改：同tick内ABI/profile值改变又恢复不保证发现，持续到退出/异常仍拒；重入/错frame/缺边界拒，handled exception不提前关scope，匹配return/finally和终态清理闭合。
- 本包只source/synthetic，完整M128/数值oracle/RTL资格不成立。后续0526单新臂实际结果独立保存与审查，不以本公开摘录授运行权限或替代实际记录；五block完整RTL仍0/5。

## PASS（有限实际M2历史对照）/ TEMP：tick策略真实验证（2026-10-21）

- DONE：新增 `candidates/fixed93_m2_tick_policy_validation/` 18文件审阅摘录，13份原Python和TICK_POLICY逐字保留。入树仅原件pins/hash及14 Python内存compile通过，无actual或源测试重跑；不含原ADMISSION/历史HISTORY/日志/数组/ELF，不是独立可执行验收包。
- 实际唯一单new无采样M2自然0/25.824389秒，原WNOWAIT0、PID/start ticks、reaped/group absent/cleanup闭合，无外soft/hard停线。0526新tick契约在source/ADMISSION/ARM/final receipt中一致消费，whole仍INCOMPLETE且0 full advance，不能升级为全块。
- 正式有限独审SHA087197391d897ef27b1cec68f61ad374be3713af719804de2d107a5e4b1cf1db：51已封产物6014897B、21源pins核验；33数组/presence/output与transport全等0417历史pins，8565+2211事件语义diff空，11011 opaque-ID账和4长期映射通过。完整Attention M2/error=null；不是独立数值oracle、RTL或旧逐回调防篡改等价。
- 实测loop CPU16.407840106秒/wall16.902397798秒；相对0503 frame-cache历史单次降低40.34399%/40.36511%，相对0417new CPU降低49.54556%。两种历史比较分开，不能拼成同期paired benchmark或M128/6600秒保证。
- ONGOING / TEMP：四owner方法的193静态line位置中14是真实字段/event hook；下一独立line契约拟只在同真实tick且无stickyerror时跳无产物line的深检查，保thread/owner/frame归属、所有exception和hook原context检查。该静态比例不是动态速度，瞬时locals/身份恢复检测差异必须明示。目前只准实现/合成，未实际执行新line版。
- 完整128-token block未通过，五block完整RTL仍0/5，无新硬件利用率实测。原失联运行、入口FAIL和不完整profile均保留；没有清理或重写历史。

## PASS（有限合成）/ TEMP：Attention局部真实event-line策略（2026-10-21）

- DONE：新增 `candidates/fixed93_event_line_policy/` 9文件便携原源码/patch/policy/测试摘录。入树仅pins/hash、3 Python内存compile通过，未重跑原cold或actual。五原件逐字不变，无原运行权限、日志或payload。
- 独立新契约：同真实tick且无sticky error时，Attention非hook line仅核thread/owner/frame归属后早返。所有call/return/exception、tick外、shared dispatcher与另一个listener原样；原14个真实line hook和6个scalar return消费者完整保留。hook表在构造末尾memory points都解析后建立。
- 四函数193个静态主体line位置中14个hook、179个无字段/event产出；这是静态位置不是动态次数或速度比。matrix_step的8个非hook位置原有context/opcode/col/causal检查仍在4个保留hook原样重验；同tick内locals/cheap身份瞬变恢复可能漏检，持久错误到hook拒绝，错误发现时刻可能延后。不能称旧逐line防篡改等价。
- 合成独审：两模块关系/逆AST成立，28个其余方法逐字；14原consumer CodeTypes、6scalar40槽、真实dispatcher另一listener4400line/400tick记录一致，每400tick两臂full核验均800。约1.12倍mock仅合成，不外推M2。
- 本包只source/synthetic；后续0549的实际M2单臂另行source-bound验证，不由该公开包授予运行或M128资格。完整128-token block及五block RTL仍未通过，无新利用率实测；旧失败原件不改。

## PASS（有限实际 M2 历史对照和采样）/ TEMP：event-line 验证与热点定位（2026-10-21）

- DONE：新增 candidates/fixed93_m2_event_line_profile_validation，24 文件、323459 字节；20 原源码/policy 摘录逐字保留。入树仅核 hash/pins 和 18 Python 内存 compile，未执行被摘录测试、native、模型或 decoder；不是完整独立运行包。独审 SHA d22c69a2c05a55c739244f05e6bff95cbe2c90b598b94d499e129a9f6df8929f，不含原权限、receipt、日志、数组、profile 或 ELF。
- 0549 无采样单新臂自然 0，实际 main_loop CPU 14.929663849 秒 / wall 15.390011784 秒，相对 0526 历史单次降低 9.008963% / 8.947760%。独审 SHA e8a3a19af0176278ad5708e9366a72b1fd7482c503c8c0ef51cce381a78831f1；仅 M2 Attention 历史等价，不是同期性能对照或独立数值 oracle。
- 0557 新诊断单臂自然 0，53 已封文件 6603299 字节；33 字段/presence/output 和 transport 精确匹配历史，8565 Attention / 2211 wholeblock 记录语义差分为空，11011 opaque-ID 差异和 4 长期映射单列。独审 SHA d461f9a060c755c1647464a20324af7a47a8602e653538d8ee35a9d168a3f1aa；Attention COMPLETE，wholeblock 仍 INCOMPLETE / 0 advance。
- 辅助采样 1461 samples、925 stacks，报告 overflow/truncation/reentrant loss 均 0，已恢复 inactive；一次 CPU gap 超过 50ms。仅 Python 可见栈，不能保证每物理 tick、不能把采样份额当精确 CPU 份额，带采样耗时不能作性能验收。独立 V2 热点分析的选定 leaf：audit hooks 453、Attention trace 396、dispatcher 262、Whole observe 90、native_snapshot 42；inclusive 不可相加。
- 辅助采样质量与主证据 seal 分离，安全恢复但不完整的采样可为 PARTIAL；不放松主证据或资源/恢复错误。0437 实际 FAIL 保留；R1 decoder 阻断是已撤回的静态推断，不是实际失败，也未扩宽 decoder。
- ONGOING / TEMP：下一独立四 owner frame-local routing 正在源码/真实 tracing 合成验证，只拟跳过无证据非 hook line 的重复投递，保留全部 14 hook、call/return/exception、SiLU 和异常恢复。新瞬变检测边界须明确，尚无新 routing actual 资格。
- 完整 128-token block 未通过，五 block 完整 RTL 仍 0/5，无新增硬件 MAC 利用率实测。本批仅本地小提交，不代表远端或 CI 更新；未删除临时数据、未重写历史。

## PASS（有限源码/真实 tracing 合成）/ TEMP：四 owner 局部 frame 路由（2026-10-21）

- DONE：新增 candidates/fixed93_owner_frame_routing，12 文件 195768 字节，8 原文件逐字保留。入树 checker 仅 11 pins/hash、5 Python 内存 compile 通过；不执行原合成/native。公开范围独审 SHA 0078f204dca0ce32e8c809b59269070679bf08f85325440178539bc4e738d8c3，无原权限、日志、payload。
- 新路由只在四 owner 真实 call 的原 listener 投递成功后建立，闭包不持有 frame/locals；return（包括 yield）显式 expiry、resume call 新绑、exception 后首 line 必须原投递。所有14 hook与非line事件保留，SiLU/其他53非line代码的异常恢复不改。注册generation/tuple对象/额外listener/错误状态变化回退原路径。
- 新完整性边界明确：非hook的thread/owner/祖先校验改在保留事件采样，瞬变并恢复不保证被发现；不能称旧逐line防篡改等价。原Attention29方法和原dispatcher投递body逆AST一致，不改计算或字段。
- 已封合成：cold02真实 tracing 控制投递68→25；cold03单独nested yield-from/send、两个同CodeType generator交错、14新闭包、38控制事件和25 mock hook一致，投递134→67。原cold01因负例fixture污染后续正例FAIL保留，仅修测试分离；合成约3.57倍不外推实际。
- 本提交仅source/synthetic范围；0629后续实际M2独立资格与本包分开。主线将以独立M16子链校准规模，不能算完整block。完整128-token block未通过，五block完整RTL仍0/5，无新硬件利用率实测；未清理临时数据。

## PASS（有限实际 M2 历史等价）/ TEMP：frame routing 实际验证（2026-10-21）

- DONE：新增 candidates/fixed93_m2_frame_routing_validation，12 文件 151625 字节，7 原件逐字；入树只核11 pins和3 Python内存compile，无运行代码/测试重跑。公开scope独审 SHA 61c66e4a830e6838d0c9de22283b3a300e0bb5915a59bf1bd9a24bea97149160，缺少运行依赖为有意，不是standalone kit。
- 新单臂实际自然0，外wrapper17.369538329秒，无soft/hard停线；原WNOWAIT0、parent/child start ticks、reaped/group absent/cleanup闭合。独审 SHA 6c0656877962bd643f793c2297266f972060675a8964615993986a741f3b8a3c。
- 51已封文件6011752字节；33 field/presence/output及transport匹配历史，8565 Attention+2211 wholeblock记录语义diff空；11011 opaque-ID差异与4长期双向映射核验。21source不变，routing policy/ADMISSION/ARM绑定。只有限M2 observer历史等价，不是独立数值oracle，也不恢复旧逐line瞬变检测契约。
- main_loop CPU8.033911631秒/wall8.280947779秒，较0549历史单次约减少46.19%；非同期paired benchmark、非硬件周期或利用率。wholeblock仍INCOMPLETE、0 public advance/SiLU，不能算完整prefill。
- ONGOING / TEMP：下一独立M16 Attention规模校准在准备新输入形状、计数和有限codec预算；不复用M2历史数值PASS，新大输出拟放独立tmpfs并分别核进程/驻留内存。尚未实际执行M16。完整128-token模型及五block RTL验收未通过，未清理临时数据，未push。

## PASS（有限 M16 结构/规模实测）/ TEMP：向真正完整 M128 推进（2026-10-21）

- DONE：新增 candidates/fixed93_m16_scale_validation，9文件79662B，3原源码逐字；入树仅8pins/hash和4 Python AST/compile。独审SHA e2d81d53fe997e3749ae4bdddf62db6c14326b714cd57a59301faa81f7ba7911。无原raw stream/transport/数组/权限，不是完整独立运行包。
- M16预声明synthetic Q/K/V使用原GQA形状16token/2KV heads；源阶段修正错误KV长度，实际未采用错误值。首cold使用Python3.13，保留但不作目标资格；同源补目标3.12.14的106控制+projection自然0后才新准实际，旧错误建议保留。
- 实际单新臂自然0，outer283.489771秒；loop CPU245.663893279秒/wall252.793958135秒。双流封存，268713 Attention记录、72393 whole记录（44355 semantic+28038 definition）；14592steps、1728groups、13248emits，27648read/1536write/ACK、133642driver ticks。独审SHA36f6730a381a612833cfb0163e4ab5ff438d946a4a3a63024baf90bc51ffe30a。
- 终态50文件151549377B、33字段/presence/output、全部29184transport地址/packet、源/权限/cleanup闭合。不读取M2历史作同形比较，只有结构/调度规模PASS，没有独立数值oracle或完整block PASS。child maxRSS217346048B/supervisor113025024B不相加冒充并发峰值。
- M2/M16每step约16.7–16.8ms，仅风险均摊显示M128 Attention约4小时，非精确预测；prefix/tail数量不同亦不可忽略。旧6600秒预算缺乏支持。ONGOING：真正0300 full producer→KV→Attention→tail接回已验证routing，拟新43200秒总上限、1CPU、明确新source/review/ADMISSION；尚未启动完整M128，不能继承旧GO。
- 资源：仅将可恢复Torch下载wheel188943803B完整复制到独立临时存储并多次SHA一致后移走原下载缓存，保留NumPy wheel、installed runtime、全部lock/pin及唯一证据；不建symlink，原缓存目录模式恢复。离线重装前需恢复原regular路径。本日不再另做仓库临时数据清理；没有删除已跟踪文件或重写历史。
- 完整128-token block未通过；后四block未推进，五block完整RTL仍0/5，无新MAC利用率实测。所有本批提交仍本地，未宣称远端/CI更新。

## PASS（完整入口源码/冷检）/ TEMP：真正 M128 全块已启动（2026-10-21）

- DONE：新增 candidates/fixed93_full_frame_routing，21文件374868B，15原件逐字；入树静态checker首次因缺-S主动拒绝，按-I -S -B更正后20pins/12 Python AST/compile通过，不重跑builder/native。公开scope独审SHA581d542069384554f85448ef6c07bed706869180304b5b81c36738c614a55f7e。摘录非完整独立运行包、无权限/权重/日志。
- 真完整入口保留pc0–8 producer、pc9本次K/V append、pc10–12 Attention、tail、public21完整seal后官方reference比较；不带M2/M16 synthetic输入或局部完成捷径。source-bound routing policy与233相对源码pins显式消费，原74 anchors/33 ABI helper约束保持。
- 新metadata组装555文件8900809B自然0/1.419221秒；唯一完整冷检自然0/6.422731秒，1638 runtime、46 frozen输入hash、30 reference仅stat、24监督mocks和43201采样行闭合。SOURCE/COLD独审SHA7f58d9d17829e166698fa72e33d54dc950666fe3b4a035e15fb2b59ec694f845；没有以冷检冒充native/数值通过。
- 新预算明确43200秒总上限=43185共享work（含计算和postseal比较）+5cleanup+10监督收口，单CPU、原2GiB门。保1秒/2048B采样不削字段，新owned22178896676B、fresh门22715767588B。12小时是上限，不保证完成，未继承旧6600权限。
- ONGOING / TEMP：2026-10-21 07:49:01 UTC新唯一全块实际进程启动。source SHA8a5c06645e0190d8e0c401173ed423deaa48e04b29d2dc2032d6e2ba2b9a0566；budget32f9aace9d9cdc7264352cc3e7f3a1873b90b1f8d48e5c60676dd2d99de0be78。当前只STARTED，不是完成/PASS；继续沿原身份监测，不重启旧失联任务。
- 完整数值、所有中间值/实际调度/缓存和终态证据仍待最终审；完整RTL0/5，无新硬件MAC利用率实测。模型通过后才冻结同刺激生成/回放RTL。该批不再清理；提交本地，不宣称远端CI已更新。

## PASS（有限源码/合成合同）/ TEMP：后续 Qwen3.5-0.8B L0 prep 小补丁（2026-10-21）

- 先核21个关键源/官方pins逐字同remote adefaa78：已有Python GDN prep/chunk支持M1..128、full_driver只开放M16/M128；public-v3 descriptor/Scala两个GDN owner限制M1。这不是上游整体不支持prefill，也不应把现有Python软件完整路径冒充Chisel多token已实现。
- 独立候选 candidates/qwen35_prep_tokens_source 共8文件70533B，单GdnInputPrepOwner源码/patch和明确合同；未改当前活全块，未改public/recurrent默认M1拒门。M>1仅内部显式maxTokens配置且16heads，Conv行12288B、packed prep行25600B、AB每token64B，整span防别名；仅末gate ACK后推进token，原16步算术顺序不改。
- 已封17组轻量源码/数学布局/ACK合同替身检查自然0/0.457241秒，目标Python3.12.14，9输入前后pin同。独审SHAe896b24531e665de3142e394b0b4248d09b397704b7436c6df9f046f772eef5c。入树仅8pins/hash与Python内存compile，未重跑合成、未编译Scala、未生成RTL、没有真实握手或数值验收。
- 该补丁仍TEMP硬件待验证，逐token prep不是chunk64 recurrent，更非完整L0 prefill通过；固定资源下每token源码计195read/400write，不是实测周期或系统利用率，80/90%目标没有新PASS证据。后四实际仍未启动。
- 当前Qwen2完整M128保持原唯一运行，尚未终态。本批本地提交，不宣称远端更新；不再清理数据。


## INCOMPLETE：完整 M128 执行及清理 UNKNOWN（2026-10-21 12:12 UTC）

Qwen2 fixed93 M128 原运行连接中断，恢复句柄不可用。最后监督记录 12:04:40 UTC，最后计算进度 Attention / pc12、10 个 public 节点完成；没有原进程退出、清理或完整产物封印。本次既不是已证算术 FAIL，也不授予完整模型、数值或 RTL PASS。五项完整 RTL 仍 0/5。不得将旧 M2/M16 子链资格升级为完整 prefill。

原候选、输入和证据保留，不读取未封存数值流、不盲目重跑；只沿可关联原身份的监督终态或平台记录恢复。普通开发及独立轻量测试继续。脱敏状态及哈希在 candidates/fixed93_fullblock_execution_unknown/；公开包 manifest SHA256 533a1fa26b4911bf5547405f8298f188fcb5e7cf59ffbd5c16b6f56d8a46392e。本批仅记录状态，无新增模型测试或 RTL 作业，无临时文件清理。


## PASS（仅 Scala 编译）：Qwen3.5 Prep 多 token 补丁（2026-10-21）

对已冻结 Prep 补丁及原支持源共18文件完成一次离线 Scala 编译。launcher 内部31.116176秒，compiler监督30.496078秒，自然退出0；89个class/843199B，4个预期Prep类齐，338输入before/after一致。实际独审 SHA256 681d3b16acd0d2c1e4b9afe478b5da1a66a13094c05384710992a1c717a47708。原WNOWAIT自然0后清理组并reap，cleanup confirmed，无timeout；不能将cleanup中的kill_attempted误解为编译强杀。

精确资格仅SCALA_COMPILE_ONLY：未执行Chisel构造/展开，未生成RTL，未测试真实ACK、数值或完整GDN/M128；公共M1及recurrent门未改变。Qwen2先前完整运行仍执行/清理UNKNOWN，五RTL仍0/5，无新MAC利用率实测。

复现命令模板、原runner源码摘录、相对输入pins及限定摘要位于 candidates/qwen35_prep_scala_compile/，8文件129291B，manifest SHA256 6a0b67b123a910b0aaec5ea49dda49a0d2c4f02a37e8cf14ac5f283a87da8075。机器冻结计划、工具二进制、class与raw logs不提交；原launcher缺机器计划不能直接运行，命令模板不等价复现原监督。未push，无新增CI，无清理。


## PASS（仅源码/整数布局/Mock ACK）：GDN chunk64 独立协议与地址计划

新增 GdnChunkProtocol.scala 与 GdnChunkAddressPlan.scala，固定H16/D128、M16/M128，24矩阵SSA私有布局与阶段依赖；复用既有Host M1双根fence，不重造持久根提交，不改公共/recurrent拒门。scratch容量M16=13959168B、M128=26869760B，stateIn/stateOut各1048576B且保持FP32。仅Bundle与BigInt声明，非RTL地址生成器、ACK tracker、算术owner或Vector端口。

17组纯stdlib controls一次自然0：外0.314185912秒/内0.232493719秒，29内置pin前后同。PASS仅源码字面量、独立整数公式与Mock ACK合同，不执行或编译Scala方法、不证明真实握手/数值/chunk prefill；该新批Scala资格仍TEMP。独审COLD_REVIEW SHA256 58c7aee70ec6219ca224eb30d4fa4030c5ba804ac3f5005fa6b8386a1eec925c。

公开7件43486B在 candidates/qwen35_chunk_contract/，6源manifest SHA256 5380d72d8d4c28cc69e27dc566b932889bf479e0befc9e31e0a9407f61aa90b2；额外TEST_SCOPE SHA256 9444d0841a343421659336d6a00e9fa5eca2e617719c06e88aacd3c6a8d24665。Qwen2完整运行仍UNKNOWN，五RTL仍0/5，无利用率实测提升，无push/新增CI/清理。


## PASS（仅两源 Scala 编译）：ChunkProtocol / AddressPlan

2026-10-21 两源独立编译一次自然0，launcher内部9.967406827秒，compiler监督9.417799秒；27class/124993B，323输入before/after一致，39封闭文件578057B均核。原WNOWAIT自然0、reaped/group absent/cleanup确认，无timeout。独审ACTUAL_REVIEW SHA256 8a919685a8f65e03eebd5293d383a8c2d35a0356ae6c53548774d0af6935e579。

PASS只限SCALA_COMPILE_ONLY，未执行AddressPlan方法、Bundle/Module构造、Chisel展开、真实ACK/算术/prefill或RTL；没有新MAC实测。两源不带Host/HardFloat，不改公共门；Qwen2原full执行/清理仍UNKNOWN，五RTL0/5。

复现模板/原runner摘录/相对pins与限定摘要在 candidates/qwen35_chunk_scala_compile/，8件125648B，manifest SHA256 cb80d6cdf65cb0ed63d78b0168e2e045e4db9438a3ddcec76c5d05aa1a328ae3。排除机器plan、工具/class二进制、raw日志及重复Scala源；非开箱即用完整closure，模板不冒称原监督复现。未push，无新CI，无清理。


## PASS（仅真实 Scala 地址计划求值）：13组行为测试

2026-10-21 原 AddressPlan 方法实际JVM求值通过：13组、161258次断言求值、1090次预期拒绝；不是161258个独立case。编译9.92845秒、行为0.945938秒，launcher总11.517577852秒；两阶段WNOWAIT自然0/已reap/group absent/cleanup确认。354输入前后同，中间只额外核原27class与新2class，不称354中间全hash。1330条类加载记录来源核实，行为classpath无Chisel，未见Bundle/硬件包。独审ACTUAL_REVIEW SHA256 33bec671116fd6af252f718454f06da41837c6e397606dd5cd82a99858a10eeb。

通过范围为Scala地址/容量/边界/阶段字节义务，不是实际ACK、数值、prefill、RTL或利用率。Qwen2先前full仍执行/清理UNKNOWN，五RTL仍0/5。

公开9件173615B位于 candidates/qwen35_chunk_scala_behavior/；manifest SHA256 9070ef26c09376c92bfa08017bfaeeb55c9c2f4d5bad7720d623a05a23700600。含原测试源码/runner摘录及复现模板、相对pins，排除机器plan/日志/class，非完整开箱closure。未push，无新增CI，无临时数据清理。


## PASS（仅 Python 对应模型/源码控制）：chunk 私有状态搬运 owner

新增独立 GdnChunkStateTransferOwner.scala，使用原512bit固定64B MemoryRequest/Response，单outstanding；仅每head的cold零填initial、warm复制stateIn、末chunk私有next_state搬出stateOut。每条1024拍，成功write ACK后推进；失败可能留下部分私有写入但不发布，held终态冻结后锁定，恢复需transport联合排空/复位。原Response只有data/tag/error、无nbytes，不虚构响应长度检查。公共M1/recurrent/Host根fence未改，无额外Vector算术资源。

16组纯Python对应模型/源码控制一次自然0，12条合成完整1024拍路径，17内容pins前后同；外0.662024925秒、内0.579626秒。不是Chisel实际ACK/数值/RTL验证；没有AS/CPU/affinity或RSS实测收据，不宣称资源峰值。owner Scala编译仍TEMP待验证。独审COLD_REVIEW SHA256 ef65cf5052b2846931ca962b6c7077867f719b8e4f1561e0a89a59f7c3a6dcf9。

公开8件84075B在 candidates/qwen35_chunk_state_transfer/，原7源manifest SHA256 9f0bf9b848a7fe5db706f395f574652fba5aa10e1e56d43522f599779c1fcd7e，单列TEST_SCOPE SHA256 4ffc537aa0fc227332f6328f0b6a04858bf8f26487f276c09daca5a7d4e67ba9。Qwen2 full仍UNKNOWN，五RTL0/5，无新的MAC利用率测量；未push、无新CI、无清理。


## PASS（仅四源 Scala 编译）：私有状态搬运 owner

2026-10-21 四源一次编译自然0，launcher内部16.588148327秒；51class/277143B与全部63封件746367B核验，326输入before/after完整一致。WNOWAIT自然0之后组清理、reap/group absent/cleanup确认，无timeout，不以kill_attempted清理记录误判被杀退出。实际独审 SHA256 3cd8d101cad9cc2c7be5e40f42203fa6f12f95246c91d7d3db46d32dcf0d1f09。

仅SCALA_COMPILE_ONLY，不执行Module、Chisel展开、真实Memory ACK、RTL或GDN算术；不能称已集成Host或完整prefill。Qwen2 full执行/清理UNKNOWN与五RTL0/5不变，无MAC实测提升。

公开8项130509B位于 candidates/qwen35_state_transfer_scala_compile/，manifest SHA256 79534496d8728b38deef64bb1df7c299e47081046e71d39beb02e5f773945857。原runner摘录/相对pins/复现模板非完整机器closure，不提交机器plan/raw日志/工具/class。未push，无新增CI，无清理。


## PASS（仅单 owner CHIRRTL 前端）：保留原后置 FAIL

R1 两个JVM自然0且cleanup确认，已生成84930B CHIRRTL，但后置类名检查只接受带数字Lambda序号，误拒当前JDK21无数字格式273条；原AFTER缺失、整体FAIL保留，不以产物存在补PASS。R2只修精确冻结宿主的格式/来源检查，未知类不放宽。21组纯解析控制通过；第一次root wrapper CPU9硬限与脚本10冲突，在测试前退出，保留后改匹配10/10，不隐去前置错误。

R2唯一实际总11.457736474秒、双自然0/WNOWAIT/reap/group absent/cleanup闭合，381输入前后全同；51原class及3emitter类核验，17普通/273隐藏类来源与宿主精确一致，exec/network/guard replacement尝试0。真实构造一个owner并检查64个IO叶，单CHIRRTL84930B，SHA256 74cae2f313e575d16418b61592e0c7e083781f78fd5980368b1fb60de74e595e，与R1产物同。实际独审 SHA256 5af1a9bea2eb177e47be114401d54e5ab8f0c120335fc4819f615446e67db4e1。

仅CHIRRTL前端构造/展开资格，生成硬件中间表示但未运行firtool、未生成SystemVerilog、未进行RTL仿真/真实ACK/数值或完整chunk；五RTL0/5、Qwen2 full UNKNOWN不变。

公开12件200425B在 candidates/qwen35_state_transfer_chirrtl/，manifest SHA256 da8f37cf8e9203ff097d89a31533921e796e9a3409c45679442b85ae45eb315b，含原emitter/runner/修复diff/复现模板/相对pins，排除机器plan、IR、日志、工具/class。非原完整监督closure。未push、无新CI、无清理。


## TEMP / INCOMPLETE：真实 Treadle owner 测试源码，依赖未齐

新增显式 Treadle 的 GdnChunkStateTransferColdSpec.scala，直接实例化真实owner而非Python替身。仅cold M16/head0、1024次固定64B零写/ACK、双向背压及8周期held done；6399 active/6412显式step是源码推导，尚未编译或执行，不记测试PASS。静审 SHA256 175060f6ba0a407aaa7115e9df00c53a4193de4a5333f18c35ecb7e073657b0f 仅SOURCE_REVIEW。

已有无RTL解释路线：chiseltest6.0内置Treadle2/firrtl2 LowForm，但当前锁106 JAR仅可复用81，缺25项19329566B。官方repo.maven.apache.org不在当前环境允许出站域，零网络尝试；这不是已发生DNS/HTTP失败。未换代理、未绕过、未安装；原87工具闭包不变。私有firtool1.62.1实际存在，不称缺失；Verilator/VCS后端仍缺。

公开8项53926B在 candidates/qwen35_state_transfer_treadle_test/，manifest SHA256 862c31ebc4e53120547bb79f23b774af52de84721390736a99ebcc4b7514254d。包含精确官方依赖URL/pin、原测试源码及限定状态，不含机器计划/二进制/日志。未授JVM/Treadle实际PASS，五RTL0/5、旧Qwen2执行/清理UNKNOWN不变。未push、无新CI、无清理。


## PASS（仅 Python 协议与模拟 Scalar）：完整 phase1 LoadPrepAndCumsum 源码

新增独立 GdnChunkLoadPrepOwner.scala，复用原GdnScalarClient Add；每head/chunk64次顺序FP32累加，完整gate/Q/K/V搬运和1600 scratch ACK，不重缩放Q。绑定prep完整资格和initial/上一chunk phase16+17同身份链，不增Vector资源、不改公共M1/Host/fence，不实现derived/exp。exact subnormal不误作underflow拒绝。

14组纯Python模型/模拟Scalar一次自然0，4完整合成轨迹，24内容pins前后同；外0.548627865秒/内0.458691秒，末held模型3周期。Scalar以整数binary32 RNE替身返回，不是独立硬件FP32验证；4192/10383/6592/16383为模型槽计数而非实测RTL周期或利用率。未编译Scala/运行Chisel/真实ACK/完整prefill。实际独审SHA256 f7fa65b26eae561ca045d3613efefb2b7b585f4928b9ba518e8ee0d849b6068f。

公开9件91077B在 candidates/qwen35_chunk_loadprep/，manifest SHA256 332fec149550b035ed02085377a126513afeaa02389aa83fa8366b9d511ad5d7。原六源保持字节，原README的未测试状态是封源前快照，新增TEST_SCOPE记录实际限域；排除机器命令/原manifest/日志，非独立完整运行closure。Scala编译仍TEMP，五RTL0/5、Qwen2 UNKNOWN不变；未push、无新增CI、无清理。


## PASS（仅20源 Scala 编译）：LoadPrep owner

20完整源（含13 HardFloat及原Scalar支持）唯一编译自然0，总29.268740754秒；116class/950518B、23必需类型齐，342输入before/after内容与身份同。WNOWAIT自然0后组清理/reap/group absent/cleanup确认；未将清理kill_attempted误报为强杀。独审ACTUAL_REVIEW SHA256 d99fe81838ade88d28f1da89067978b38c7c53bb3d278d6d29eecae03be0acdb。SOURCE有限GO在启动前已发，完整SOURCE收据封存晚于启动，如实分列不倒填时间。

PASS仅SCALA_COMPILE_ONLY，不执行Emit App/Module/CHIRRTL、真实Scalar/ACK或数值；五RTL0/5、Qwen2full UNKNOWN不变。公开8件132608B在 candidates/qwen35_chunk_loadprep_scala_compile/，manifest SHA256 6e6a74e54f27801a7e4c749226fc49ce144a2d2250f4c22ab1b0d706fa9b5a0b，复现模板/原runner摘录不是完整冻结机器closure，不提交工具/class/机器plan/log。未push、无新CI、无清理。


## PASS（仅单owner CHIRRTL前端）：LoadPrepAndCumsum

唯一实际66162自然0、总9.002297696秒，462输入前后完整身份与内容同；116原类+3emitter，双JVM WNOWAIT自然0/reap/group absent/cleanup确认。独立类加载核19输入普通类+3emitter、385隐藏类/14精确宿主，未加载HardFloat/gemmini/BlockScalarFloat；exec/network/guard replacement0。

实际构造单LoadPrep owner、生成CHIRRTL131416B，SHA256 b95431cf614e93810812bb1c313c1ff3dee456eb8ff715956f8dd947900b139f。独立递归解析确认97端口叶（67输入30输出）、单模块无子实例/存储；实际独审SHA256 b1eeac5a9bff69648a903bdbcc56207370ad3d29ded6ed2d4a52c0821649eb57。27纯parser控制是先行限定测试，不与前端混淆。

仅Chisel构造/CHIRRTL前端，未运行firtool/SV/RTL仿真、真实Scalar/ACK/完整prefill，无MAC测量。五RTL0/5、Qwen2full UNKNOWN不变。公开12项99140B在 candidates/qwen35_chunk_loadprep_chirrtl/，manifest SHA256 49bc4527eb1b7cb183ff70eb3747f4abf61c1689496c734de93ba478b9ecdcaa；复用已有342pins加120增量，不复制IR/class/生产源/机器plan/日志。原runner摘录非完整可直接执行closure。未push、无新CI、无清理。


## PASS（仅Python协议/模拟服务）：DerivedAndPair phase2源码

新增独立owner借现Scalar Exp4及同16路ALU Loan Add1/Mul2，不新造exp/Vector、不改Host/public接线。保留gates63补读、phase1完整资格、256B四槽全部tuple结果算完再写、末2816ACK后带完整context私有decay有效。Loan abort/reset不保持高等terminal；真实错误response退役后held done再锁定，失败不授drained。

15组纯Python对应控制唯一自然0，外1.33311112秒/内1.260561秒，32内容pins前后同；两合成完整轨迹各13410事务：3681读、2816写、2144Add、2209Exp、2560Mul16。原序与payload在线对照使用模拟服务，共享helper不是独立FP32DUT；subnormal部分测试为注入接收门。26980 modelcycles不作硬件周期/全block利用率。独审ACTUAL_CONTROLS_REVIEW SHA256 78795c2a5e06f6ec4f2f163d6fac4090c17bbea3f95027f3c42106762f2335ba。

公开10件112580B在 candidates/qwen35_chunk_derived/，manifest SHA256 503afae0679ea4952962c1030b0a5a0dd9bcdd210251881fadb0378e6eba9d64。原7源字节不改；排除机器命令/原manifest/日志/数组，非独立运行closure。Scala编译/CHIRRTL/真实Scalar或Loan/ACK仍TEMP未验，五RTL0/5、Qwen2full UNKNOWN不变。未push、无新CI、无清理。


## FAIL保留 / PASS仅R2 Scala编译：DerivedAndPair Enum绑定修复

原26源编译自然exit1，唯一诊断位于23名链式解构Enum(23)，报object <none> is not a member of package scala。349 BEFORE匹配，0class，AFTER未执行；cleanup确认，无资源超限。Scala多绑定展开问题仅推断，未泛化证明根因。原失败独审 SHA256 4215e3197706a4f2552cad3742376afe60cd2ee7e6bf2c61ba5ec69c1e4d2b25 保留。

R2仅一次Enum23后原序0..22显式命名，逆替换整owner恢复原SHA；模型及24外源不变。15组纯Python控制重跑自然0，34内容pins同，两轨迹全部字段/hash与原相同，限模拟服务。新26源实际编译25418自然0/33.930169611秒，349输入前后完整身份同，142class/1467305B、41必要类齐，WNOWAIT自然0/reap/group absent/cleanup确认。实际独审SHA256 1486feb0998506858a6205d9d318f550e8898c45c291c5950a719a2bd6bccf9d。

PASS只Scala编译；未构造/CHIRRTL/真实Scalar或Loan/ACK/数值/RTL，五RTL0/5、旧Qwen2 UNKNOWN不变。公开11项57570B在 candidates/qwen35_chunk_derived_r2/，manifest SHA256 f202b82ba4c26c4d26aa57bfd210c1807d247b2dd37a44f4977447468bebd63e；仅新owner/patch/绑定表/测试diff/runner/相对pins及摘要，不重复模型或私有日志/机器plan，非完整可直接运行closure。未push、无新CI、无清理。


## PASS（仅单owner CHIRRTL前端）：DerivedAndPair R2

唯一84772实际自然0/总10.694218065秒；495输入before/after含完整身份同、142原class+3emitter逐hash，双阶段WNOWAIT自然0/reap/group absent/cleanup确认。独立类加载仅24输入普通+3emitter、655隐藏/18限定宿主，无Loan/MemoryEngine/Scalar/HardFloat服务实现。29纯parser组是先行限定控制，非硬件测试。

单CHIRRTL213402B，SHA256 bb403c278d839b9dbd3dcb03e7e4a576dfeb4d37b34655cec150c27f3797e7ce；独立解析117端口叶与原源码全匹配，单owner无子实例。实际独审SHA256 7164c0bf279e5af50b2d68890f2f4ecb6e698d734951ce759afc3d1791f763bd。只构造/CHIRRTL前端，不是实际Loan/Scalar/ACK/算术或RTL仿真/完整chunk；五RTL0/5、Qwen2full UNKNOWN不变。

公开12项109622B在 candidates/qwen35_chunk_derived_chirrtl/，manifest SHA256 ee247fc9e4a2ac64c824143c85f57474e283129f747a9a74b7666135fa08c88d；复用base349相对pins加146增量，无生产源/模型/工具/IR/class/日志重复。原runner仍非完整可直接执行closure。原Enum解构FAIL保留；未push、无新CI、无清理。


## PASS（仅源码/Python模拟协议）：phase3/4单job转置

独立owner复用一个1KiB tile，单job内部phase3末512ACK后才能phase4；每阶段512读/512ACK/32768B，逐读finite拒NaN/Inf，±0/subnormal按bit保留，无算术服务。phase4失败保phase3历史checkpoint，但整体drained/decay不授资格并锁定，末ACK与held终态明确。

18组Python对应模型控一次自然0/外0.349906391秒/内0.269774秒，两完整2048模拟事务轨迹，26内容pins+manifest前后同。首次exec CreateProcess传输拒绝、输出目录不存在后才创建成功执行，不称第一次测试失败。资源记录CPU10/10/AS256MiB/1CPU/外10秒/单文件FSIZE1MiB；4MiB为提案及末态4848B核限，非运行中aggregate实测，无RSS测量。独审SHA256 ff71e9b2fa99212652b5228df1d1e43748edc2c9eeee5684421e85a7409fa252。

公开11件88698B在 candidates/qwen35_chunk_transpose/，manifest SHA256 46eba3dde29a0ae68f891f349f0bb9802ef32aebab9f1a4b377618e96d9e7f9b；8原件加限定scope与清单，排除机器命令/原日志，不是独立运行closure。Scala编译/真实ACK/RTL均TEMP未验，五RTL0/5、Qwen2full UNKNOWN不变。未push、无新增CI、无清理。


## PASS（仅27源Scala编译）：转置owner

唯一35789自然0，总34.326824278秒；351 before/after含stamp逐项同且接固定plan，146class/1563484B实hash/magic核同、45必需subset齐；158封件2121598B库存闭合。原child确权WNOWAIT自然0、reap/group absent/cleanup确认，无timeout。独审ACTUAL_COMPILE_REVIEW SHA256 65b91657b5bb6f64b86ac792c488a45e6f7c1af8c8c96b28eb926610495c1cf0。

仅SCALA_COMPILE_ONLY，未运行Module/CHIRRTL/真实ACK/RTL/数值；五RTL0/5及Qwen2full UNKNOWN不变。公开9项30160B在 candidates/qwen35_chunk_transpose_scala_compile/，manifest SHA256 b0a5a752372b3537f98bf4248239ea56f256bd77062634acce447f4147eced61，旧349pins引用上包仅新增2逻辑pins，无生产源/模型/工具表/机器plan/日志重复，非完整可直接执行closure。未push、无新CI、无清理。


## PASS（仅单owner CHIRRTL前端）：phase3/4转置

唯一53452自然0、总9.67059275秒，501输入前后含stamp同，146原class+3emitter全hash，两阶段WNOWAIT自然0/reap/group absent/cleanup确认。独立解析4839加载行仅17+3普通类、358隐藏/13精确宿主，无服务实现。

单CHIRRTL139800B，SHA256 6949334f3288ab6024a01dabaa2fc3e5148b69f80bfd841a9201cec3f49f47a8；独立递归bundle/flip核109端口叶（57入52出），tile为UInt512×16共8192bit寄存器payload，无memory/子实例。独审ACTUAL_REVIEW SHA256 b5c97e928f79f2a1b6f90438bbbd807282fe48ce8997da0e9bc1054a049315bf。仅前端构造/声明，不是实际ACK/数据转置/RTL仿真，五RTL0/5、Qwen2full UNKNOWN不变。

公开12件108677B在 candidates/qwen35_chunk_transpose_chirrtl/，manifest SHA256 c7cb1bb2244bc4cdd0acbe30bc2fc9a6e3260fa2920578bce6337ad4b826d447。引用旧351pins+150逻辑增量，不复制生产源/工具表/IR/class/机器plan/log；原runner非完整运行closure。未push、无新CI、无清理。


## PASS（仅源码/独立软件参考）：隔离strict FP32单lane原型

新fullFP32 Pre复用原Mul/Post/Round一条算术链，strict Mul后先舍入并判fatal/nonfinite，成功才p×+1+oldacc完成独立Add舍入；Mul符号零、逐pass flags及held/reset边界明确。BF16 raw单FMA为独立模式，原BF16源/阵列未改，不增第二算术链；尚未接16词故障屏障/全阵列/完整UT。逻辑资源数量固定的新配置不代表原综合面积/Fmax/netlist不变。

18纯Python组一次自然0（20定向+256固定seed），整数RNE模型与Fraction邻值参考无共享舍入helper，外0.132981311秒/内0.03881秒；30内容+manifest前后同。仅软件参考与协议模型，BF16 NaN/Inf为注入raw回复门而非实际非有限算术回归，未运行硬件/Scala/RTL。独审ACTUAL_REVIEW SHA256 8220c8d2ede6d732ca8367895284feba93e3e55a55bd420b8552bce79681a275。

明确集成阻断：0x00800000×0x3f7fffff精确积(2^24−1)×2^-150，RNE交付0x00800000；原HardFloat源码tininess-after规范预期UF|NX=3，旧vector16.cpp final-abs修正给NX=1，fatal30接受不同。原型保HardFloat规范，不静默修改旧CPP/旧证据，不称旧软件error边界等价；该差异不是硬件实测，原型PASS不能解除未来集成阻断。

公开16件75428B在 candidates/qwen35_strict_fp32_lane/，manifest SHA256 7d1a6abb9f595dd3a3151f6c02709d4b0b755e07866491bf531bbb24e3ce9aaf，排除机器命令/raw日志/工具/IR/权重，非完整可直接运行包。五RTL0/5、Qwen2full UNKNOWN不变；未push、无新CI、无清理。


## PASS（仅10源Scala编译）：strict FP32隔离单lane

唯一85081自然0/17.330634545秒，331输入before/after全字段同并接plan，55class全hash/magic同、29required齐；总67封件926956B。原leader身份采样同，WNOWAIT自然0/reap/group absent/cleanup确认，无timeout，compiler log空；观测自然退出后组清理不作强杀PASS。独审ACTUAL_COMPILE_REVIEW SHA256 2586ff6f604b84d6d95d7a7a5c4f21a95f53afdb1a4159fa289c0b6b375a8a1a。

仅SCALA_COMPILE_ONLY，不构造/执行原算术链、不授硬件数值或RTL/阵列资格，UF3与旧CPP1的集成阻断保留，五RTL0/5及Qwen2full UNKNOWN不变。公开9件29028B在 candidates/qwen35_strict_lane_scala_compile/，manifest SHA256 7db2ae55d0feda03dc4f90542f0b477fc4bdf0b143a2f394a55ae674320480b0；无重复生产源/完整工具表/机器plan/class/IR/log，非完整可直接运行closure。未push、无新CI、无清理。


## PASS（仅隔离单lane CHIRRTL前端）：原算术链复用结构

唯一24570自然0，总10.785390577秒，390输入前后完整身份一致，55原class+3emitter核验；双阶段自然0/WNOWAIT/reap/group absent/cleanup确认。真实CHIRRTL319324B，SHA256 ea7b84533c96641771bd58ba97a10898d428fc6782b1ced726442ada0320eb7d。

独立结构核9模块8边全可达各一次、唯一24×24变量乘法、27顶层叶（130/124payload）、12顶层寄存器553bit；不沿用无子模块门。独审ACTUAL_FRONTEND_REVIEW SHA256 b86ba2968769af2fcb96ea2fe202e95dd5e0dfe91aa03fa5d1d6368fb363924c。45纯parser正反例为先行fixture测试，非生成硬件行为。

仅构造/CHIRRTL结构PASS，未执行数值/flags/握手/RTL或16lane阵列，面积/Fmax不继承；UF3与旧CPP1集成阻断保留，五RTL0/5、Qwen2full UNKNOWN不变。公开14项112395B在 candidates/qwen35_strict_lane_chirrtl/，manifest SHA256 a07c5330d5f1d0a3b6bab5b9bdcdd3a69444749dab94dbd486ef78e1a92a67e9。相对pins/原源摘录不含IR/class/完整工具表/机器plan/raw日志，非原完整运行closure。未push、无新CI、无清理。


## PASS（仅原C++软件诊断）：UF边界策略差异实测

唯一92564自然0，总1.278891735秒；原vector16.cpp逐字复用、24finite刺激和3原mask30 batch，独立第二TU原生运算/Fraction值参考/HardFloat源码flags规范分列。正负minnormal边界输出00800000/80800000，原CPP postfix flags=1，raw-host实际flags=3，HardFloat源预期3；原mask30 issue=[1,0]实际继续Add。tiny-zero/overflow停Mul且Add sentinel保持。24交付值同Fraction，仅01/02有flags1/3/3差异。

2361输入前后全同，真实-M依赖121项（两个TU73/120）全在预pin集合，23终态文件2261062B全核；三阶段自然0/WNOWAIT/reap/group absent/cleanup。MXCSR8096→8098仅DE sticky新增，标准FE/control保持，不修改FTZ/DAZ。独审ACTUAL_REVIEW SHA256 38766c8172145b746de7a5d133bd430afa74df7cb38d1aeb2eba351fde7a7383。

这是原C++软件primitive策略差异的实际证据，raw探针是第二次独立运算，不冒原API内部采样；仍未实测HardFloat/RTL flags。旧源/旧收据不改，UF契约集成阻断不解除。公开10项50874B在 candidates/qwen35_uf_native_diagnostic/，manifest SHA256 d069502fb1789ed076569817aa4025bca08c558ad71fd9640a3873c8cace1feb，无机器plan/工具表/二进制/原日志，入口缺冻结计划不可直接执行。五RTL0/5、Qwen2full UNKNOWN不变；未push、无新CI、无清理。


## PASS（仅隔离软件修复）：finite Mul的UF整数判据

新隔离CPP副本以≤48bit精确乘积与T=(2^25−1)×2^-151严格小于比较，再与原本次FE_INEXACT相与得到UF；保原结果/其他flags/顺序/Add与nonfinite路径，不依赖host rawUF或finalabs。R1把tiny提前求值造成旧NX0短路语义改变，源码hold且从未执行，原件保留；R2只把选择放回原NX&&右侧，逆patch恢复旧CPP全部字节。

唯一10672新副本实际自然0/总1.199853478秒，70例value/flags同独立Fraction/HF源规范，5batch。正负边界01/02实际flags3、issue[3,0]止Mul且Add sentinel未改；阈值恰等03 flags1继续Add，精确subnormal09 flags0继续Add。旧24列沿历史已封实际，新增46旧列仅源码预测，不重复加载旧ELF。新增N44差异不冒充旧实测。2370前后同、121依赖subset、23封件2304028B全核，三阶段自然0/WNOWAIT/reap/cleanup确认；旧CPP SHA不变。独审R2_ACTUAL_REVIEW SHA256 db6147fd48e56d8375ae30e7b59b6eb9c8bb4ad43f46cabb22ca44a329324285。

仅隔离finiteMul软件参考修复PASS，不自动替换完整模型或授HardFloat/RTL flags资格，硬件及整模集成仍阻断。公开12件47208B在 candidates/qwen35_uf_predicate_r2/，manifest SHA256 37195330ca9e1e491c8b38caa6862800c5cdd8242047f52503c2ba707aa25ac5；含新副本/patch/刺激/有限摘要与相对pins，无重复模型/工具表/原log/ELF。五RTL0/5、Qwen2full UNKNOWN不变；未push、无新CI、无清理。


## FAIL保留 / PASS（仅软件参考wrapper）：strict两pass契约

首次1954自然exit1，加载wrapper的dataclasses触发安装后的no-pyc门，尚未mock/CDLL/trace；714仅BEFORE，AFTER缺失，cleanup确认。R2只在guard前精确预加载并核dataclasses/fractions原runtime来源，保持fresh pycache/-B及guard后全拒pyc，wrapper/ELF/刺激/mock/driver不改；旧FAIL保留不作数值FAIL。

唯一R2实际自然0，总0.547398621秒，714前后完整一致/12封件801596B核验；52请求（44唯一）99真实trace=52Mul+47Add，46成功+5Mul fatal不发Add+1Add fatal保诊断不commit，12非finite前拒无trace。13组93项明确MOCK，不混实际native；原ELF未重编，标准FENV sticky/controls同、DE0→1另列，原child身份/WNOWAIT/reap/group absent/cleanup闭合。独审R2_ACTUAL_REVIEW SHA256 cd2eddc2d601250dfa0a0a352e092a99d1f441387f3dcad7d4e575ab0dfa4437。

仅隔离finite/RNE/fatal30软件参考wrapper，不替旧op6/Exp/16lane/整模，也不授硬件flags/真实握手/RTL。公开12项66313B在 candidates/qwen35_strict_reference/，manifest SHA256 5f9b07a568d70ba1770e8c05ce453428477f812c69752be927e0c9dbededafc9，排除机器plan/工具表/ELF/rawlog/重复模型，非standalone。硬件与整模集成仍阻断、五RTL0/5、Qwen2full UNKNOWN不变；未push、无新CI、无清理。


## TEMP：Strict FP32 lane 真实 DUT 回归源码（2026-10-22）

新增 candidates/qwen35_strict_lane_regression：实际 StrictFp32MatrixLane 的五组 ChiselTest/Treadle 测试源码，覆盖52个冻结请求、15字段、逐pass flags/valid/commit、有限请求3周期背压、12非有限预拒绝和3模式/编码拒绝、9个复位位置、退休同沿禁止新请求及恢复。每pass4周期、双pass8周期为待硬件验证期望，不是实测。

PASS仅限已实际运行的 Python Fraction/fixture逐字一致性检查；独立源码审查未见阻断缺陷。Scala编译、展开、Treadle和RTL均未运行。冻结输入实际去重41=20+24−3，纠正前节44的计数说明；历史52请求、52Mul+47Add=99真实软件trace不变，旧原始证据不改。

依赖阻塞归因更正：此前25个Maven缺件从未提交网络请求，不是实际访问被拒。本次通过正式 require_escalated 路径尝试下载，沙箱启动在Python执行前失败；独立输出目录不存在，无HTTP结果、无下载成功，不修改受限系统路径或绕过。下载器源码已准备，保留失败记录；缺件仍未补齐。五block完整RTL仍0/5，Qwen2完整M128终态UNKNOWN，未push、无新CI、无清理。


## TEMP：单 lane 测试驱动与 Treadle 官方源路径核查（2026-10-22）

新增 candidates/qwen35_strict_lane_runner_source/：强制准入与源码pin、终态容量复核、有界清理及失败receipt保留。实际运行8项纯Python负例/mock检查通过，独审另做5项phase状态mock；无真实子进程/JVM/网络/硬件测试。故意注入inventory失败的FAILED记录是负例，不是硬件失败。公开不含机器PLAN、依赖二进制或私有路径，非standalone硬件运行包。

核官方chiseltest固定d764fdf74652426b57c6eae00d71eac19effd224的13个源文件并验证Git blob身份：显式Treadle路径为ChiselBridge → Scala firrtl2 low lowering → JVM解释器，选定路径无需firtool/SV/原生编译器，但可能生成low FIRRTL。仅SOURCE_ROUTE_VERIFIED，不是运行、数值或资源实测；相对targetDir及无blackbox/extmodule结构门仍须实际执行前核查，执行gate未打开。

缺少25个JAR与沙箱提权启动失败仍阻断实测；原下载失败记录保留，不绕过受限路径。五完整RTL0/5、无新整块利用率证据。无push/CI/清理。


## PASS（仅冻结旧 IR 结构预检）/ TEMP（新测试电路未验证）：2026-10-22

新增 candidates/qwen35_strict_lane_structure_gate，复用原已固定validate_ir，只加载两个必要函数，不运行原runner。27项纯Python方法实际通过（21类IR负例、6注解变体及大小/hash边界等，计数不相加冒充独立测试总数）。对既有319324B CHIRRTL / SHA ea7b84533c96641771bd58ba97a10898d428fc6782b1ced726442ada0320eb7d 的实际只读预检通过：9模块全图可达一次、8条实例边、唯一24×24变量乘法、无extmodule/intmodule/blackbox marker。

完整IR hash及旧来源/类资格回执为必要边界，旧parser不是通用FIRRTL全语法安全分析器。未提供外部注解时明确不作注解不存在的结论；提供非空注解全部拒绝。没有新展开、JVM或RTL运行，不证明新runner的测试电路等同此旧IR，也不自动打开执行gate。原IR/classes不公开，七个公开文件只含代码、pins与有限摘要。五完整RTL仍0/5、M128原运行UNKNOWN、无新MAC利用率实测；未push、无新CI、无清理。


## PASS（仅单 head 两个 chunk64 的 UT/QK 合成数值模型）：2026-10-23

新增 candidates/qwen35_chunk_strict_contraction。真正执行M128边界的两个不同chunk64、phase5/6完整64×128乘128×64收缩，按K递增、FP32乘后加分别舍入、最后乘pair，不以循环单token替代chunk。提议复用4096 Matrix lane两pass和16 Vector最终因子运算，累计4194304 Matrix lane passes/16384 Vector运算；需40960B数据存储，未证明已有SRAM可免费复用，非完整block周期或利用率测量。

R1原件保留：测试pair误用严格下三角、部分Fraction终值被零因子掩盖等覆盖缺口已修；R2模型算术源码不变，mask为下三角含对角，对角值1，不是tril offset+1。作者7测试9.903s；独审同hash前后7测试9.425s、exit0，1CPU/512MiB虚拟内存/60s墙钟及CPU限额。4210688项NumPy中间/输出word对比，12条Fraction链3072中间word+flag及12最终word+flag；5条实际Contraction定向链1280中间word+flag，但5个最终比较仅bits，不冒称flags也被比较。包括FMA/K顺序/因子位置差异、Mul/AddFatal、pair下溢、部分写回失败。

没有完整平面独立flags oracle，也不证明上游decay生成、全部head、递归state carry、完整block、异步传输、RTL或物理资源/QoR。本候选与此前49笔发布批次分开；不包含原权重/NPZ/数组转储。五完整RTL仍0/5，原Qwen2M128终态UNKNOWN。


## PASS（仅同步软件缓存复用及数值回归）/ INCOMPLETE（真实调度）：2026-10-23

同一 Contraction 实例现在跨两个 chunk64 的 UT/QK 四次运行复用两个4096-word bank与两个1024-word panel；新增同步重入所有权拒绝、部分panel读失败后复用、错误地址与复制bank身份负例。主fixture核8192个实际回调/算术事件，5120读、1024写、2048算术观察，保留4210688项数值比较。独立实际10测试12.838秒exit0，1CPU/512MiB/60秒限制，四个源码hash前后相同；旧7测试回执不改，新回执独立保存。

明确限制：上游 _matmul 是逐输出beat协程，本候选仍为整平面同步软件；未复用实际prefill调度器，未验证异步ACK、phase/chunk次序、物理端口或RTL。40960B仅提议数据存储，不是既有免费资源。五完整RTL0/5、Qwen2完整M128仍UNKNOWN、无MAC实测。远端main核f93f0c4（原49笔已发2笔），余47笔发布等待中断后确认；本修改单独本地保存。临时目录盘点423项，无清理。


## PASS（仅原协程复用与 strict 软件数值）/ INCOMPLETE（完整 owner 接入）：2026-10-23

新增 candidates/qwen35_chunk_strict_contraction/upstream_coroutine.py，直接绑定既有 ChunkOwner._matmul、_read、_write、_mul_add 实际方法，执行原 row/16列beat/K 次序。只把 _op 接到已有 strict integer FP32；不构造原 Vector16、不改原 ChunkOwner policy，不冒称已把4096-plane两bank/panel方案接进原 owner。复用既有 MemoryRequest/MemoryResponse，测试由原 TypedMemory.begin_write/write_data/acknowledge 完成实际软件字节写与ACK。没有独立仿造一份成功 ChunkResult。

作者合并14测试（原10+新4）22.175秒exit0，1CPU/512MiB虚拟内存/60秒墙钟与CPU限额。新测试完整执行一个UT及另一个独立QK矩阵，每个64×128乘128×64；共2105344中间/输出word与flags逐项对照当前两bank模型，70656个原协程请求按独立row-major地址/tag逐个核。此跨调度对照共享strict整数primitive，不是独立完整flags oracle，原NumPy/Fraction回归保留。每phase原协程35072读/256写，提议panel方案1280读/256写，均仅实际软件事务计数，不作cycles/bandwidth/utilization结论。独立同范围14测试21.505秒exit0；12个收据文件的终态大小/hash复核一致，运行期代码冻结，未做运行前hash捕获，不声称前后hash双验。新收据UPSTREAM_COROUTINE_VALIDATION_SCOPE单列，旧7项与10项收据不改。

新负例包含malformed/stale响应、非finite源、悬停写期间重入拒绝、第二写坏ACK后首beat ACK保留且不发布，以及minnormal边界strict flags3止Mul不发Add。失败物理写由测试caller明确failed-retire；adapter关闭只释放本地busy，不能替代accepted transaction drain。输出全部数据和ACK通过也保持unpublished；phase输入仍是明确合成边界，不冒称prep/decay已生产或真实M128两chunk链。

剩余接入阻断与下一步：ChunkOwner构造仍要求原PrepScalar/精确Vector16，TypedChunkDriver要求精确ChunkOwner/ChunkJob并核真实producer完整ACK、ScratchPlan和output/state双span；不能用局部phase replay伪造完整staging成功。应在既有owner中增明确默认关闭phase/算术policy hook，保留原typed driver、lease、abort/reset/drain和完整state/output发布边界，先真实producer到UT/QK有界接入；whole-plane方案另须把同步read/write改成可悬停协程并证明两bank/panel生命周期、physical ports和broadcast成本。原Vector16 CPP flags1与strict/HardFloat源码规范flags3差异仍阻断数值等价声明。五完整RTL0/5、Qwen2完整M128仍UNKNOWN；没有Scala/RTL运行、网络、安装、提交、push、CI或清理。


## PASS（仅注入相位的真实软件owner生命周期）/ INCOMPLETE（完整block）：2026-10-23

新增test-only instance hook，在真实ChunkOwner/TypedChunkDriver执行单head UT、QK各完整一相位；原tick/ports/_advance/_finish、lease、ScratchPlan、字节写ACK与drain未复制。1280合成operand beats经同driver实写/ACK后才读；admission input仅合成发布fixture，不授真实Prep/decay producer资格。每相位35072读/1536写ACK，8192终值与独立NumPy分离Mul/Add逐位相同，原中间值/Fraction回归保留。作者20项25.947秒exit0；独审20项仓库测试加3项临时边界测试共23项27.016秒exit0，1CPU/512MiB/60秒；16列明文件前后hash一致，不是完整依赖闭包。

末ACK背压、abort/reset排空、stale/malformed ACK拒绝信用、strict UF3 Numerical、terminal保持及detach/reset通过。相位耗尽必须获得原owner的Protocol失败，output/state零写，staging/publication/commit/generation均false；这是预期负向生命周期，不是fullowner成功。Vector16仅不计算的lease shell，原CPP flags差异未解；whole-plane调度、真实producer全链、完整block/RTL未完成，五RTL仍0/5，Qwen2M128终态UNKNOWN，无新利用率。保留所有旧证据；仅本地提交，远端发布仍待确认，未清理。


## PASS（真实producer软件切片）/ INCOMPLETE（双chunk及完整block）：2026-10-23

新增real_producer_slice：仅原始Conv/AB BF16与A_log/dt_bias使用明确合成fixture，原TypedInputPrepDriver实际计算/ACK/发布128-token单head Prep；原ChunkOwner._compute不替换，实际生产cumsum、decay、products、pair、transpose及head0/chunk0完整UT/QK。不注入kb/kt/pair；只以1..16活动lane strict Add/Mul适配替代实例_op，原PrepScalar Div/Sqrt/Softplus/exp政策保留，不授原生Vector16算术等价。核819200 Prep words、87040 producer words与2148512 Add/Mul中间结果。QK末ACK后接受solve_v首读再走真实abort/drain，终态Aborted、chunks_started=1/completed=0，无output/state写或发布。

首次wrapper因/usr/bin/time缺失exit127，Python未开始；只换Bash计时后首次实际2测试10.597秒通过，原失败证据保留。独审合并22测试37.926秒exit0，1CPU/512MiB/60秒。33捕获文件前后hash相同，其中26与收据28项重叠，另7Python；收据2Scala仅运行后验证，不夸称完整闭包。四个历史收据不改。仅该软件切片PASS，第二chunk/state carry、全部head、完整block及RTL未验收，五RTL0/5、Qwen2旧M128仍UNKNOWN、无MAC利用率。小批本地提交并备份，远端仍f93f0c4等待发布确认，无清理。
