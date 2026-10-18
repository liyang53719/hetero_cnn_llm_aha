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
