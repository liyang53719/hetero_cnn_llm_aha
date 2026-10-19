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
