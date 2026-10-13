# Block checklist（只读视图）

当前最终目标：Qwen2-1.5B、Qwen3.5-0.8B、Qwen3.5-35B-A3B各自典型block实际生成RTL数值通过，Matrix整block有效MAC利用率≥90%；Matrix/Vector分报，固定配置资源分母。
U00=ongoing；U01=to do。C03.3仅为E0，Q38及旧R00/整网任务保留历史并排除当前派工。

唯一状态源为 `block_checklist.yaml`；本表由 `scripts/block_checklist.py render` 生成。

| 编号 | 优先级 | 事项 | 状态 |
|---|---|---|---|
| C00 | P0 | 重建最新源码与证据基线 | ongoing |
| C00.1 | P0 | 核对当前可用归档和关键源字节 | done |
| C00.2 | P0 | 完整工作区工具与硬件资源基线 | to do |
| C01 | P0 | 冻结三模型真实forward和层索引合同 | ongoing |
| C01.1 | P0 | 现有模型合同入口fail-closed校验 | done |
| C01.2 | P0 | 固定官方revision、forward、权重index和层索引复核 | to do |
| C02 | P0 | 建立双参考和可执行精度合同 | ongoing |
| C02.1 | P0 | 精度比较器公式注册与缺失合同拒绝测试 | done |
| C02.2 | P0 | 官方双参考与每producer精度合同完整冻结 | to do |
| C03 | P0 | 解耦模型几何与矩阵tile | ongoing |
| C03.1 | P0 | 编译器派生几何和状态容量合同 | done |
| C03.2 | P0 | 实际Chisel shape/layout/frontend解耦及回归 | to do |
| C03.3 | P0 | 跨语言shape/layout测试向量与宽地址oracle | done |
| C04 | P0 | 统一typed tensor与多输入policy ABI | ongoing |
| C04.1 | P0 | 现有Command128与descriptor整数边界及字节合同加固 | done |
| C04.2 | P0 | typed tensor与多输入policy完整Host到RTL接入 | to do |
| C04.3 | P0 | 版本化typed descriptor候选与Host序列化合同 | to do |
| C05 | P0 | 将root微程序接到真实数据owner | to do |
| C06 | P0 | 超64命令与有限tensor存活集合 | ongoing |
| C06.1 | P0 | 长命令容量与生命周期控制专项测试设计 | done |
| C06.2 | P0 | 长命令实际frontend接入与全部门禁 | to do |
| C07 | P0 | 有界片上状态tile与事务提交 | ongoing |
| C07.1 | P0 | 多状态域事务提交与失败恢复控制合同测试 | done |
| C07.2 | P0 | 实际state-memory owner与片上资源及状态续算集成 | to do |
| C08 | P0 | 建立完整block公共测试与回执校验器 | ongoing |
| C08.1 | P0 | 全量tensor/state回执schema与比较器框架 | done |
| C08.2 | P0 | 真实block公共runner和全部比较域集成 | to do |
| C08.3 | P0 | E0状态事件trace到全量回执的独立交叉校验 | to do |
| Q20 | P1 | 重跑当前Qwen2双层主链保护基线 | to do |
| Q21 | P1 | 官方Qwen2 block权重与输入导出 | ongoing |
| Q21.1 | P1 | 通用权重分块打包与BF16字节回读测试 | done |
| Q21.2 | P1 | 官方Qwen2权重与真实输入导出验收 | to do |
| Q21.3 | P1 | 固定Qwen2层0真实payload与完整prefill模型前置验证 | ongoing |
| Q22 | P1 | Qwen2官方语义与批准混合精度闭环 | to do |
| Q23 | P1 | Qwen2官方完整block长度扩展 | to do |
| S00 | P1 | 通用Norm与非线性数值owner | to do |
| S01 | P1 | 有前缀GQA与partial MRoPE执行路径 | to do |
| Q24 | P1 | Qwen2真实状态续算与官方双层 | to do |
| S02 | P1 | GDN因果深度卷积真实数据与history | to do |
| S03 | P1 | GDN单token矩阵状态递推 | to do |
| S04 | P1 | GDN prefill先正确递推再验chunk模式 | to do |
| S05 | P1 | MoE router与实际token路由 | to do |
| S06 | P1 | routed与shared expert完整执行及加权合并 | to do |
| Q35A | P1 | Qwen35完整Attention分支接入 | to do |
| Q35B | P1 | Qwen35完整GDN分支接入 | to do |
| Q35C | P1 | Qwen35官方Attention加MoE完整block | to do |
| Q35D | P1 | Qwen35官方GDN加MoE完整block | to do |
| Q35E | P1 | Qwen35真实3GDN加1Attention周期组 | to do |
| Q38A | P2 | 四分支gated residual真实读写 | to do |
| Q38B | P2 | Qwen38 GDN几何与gate模式复用 | to do |
| Q38C | P2 | QSA index/summary及真正Top512 | to do |
| Q38D | P2 | QSA稀疏KV gather和Attention数值 | to do |
| Q38E | P2 | PLE ngram与稀疏行表及dilated conv | to do |
| Q38M | P2 | Qwen38 512选10 MoE真实几何 | to do |
| Q38F | P2 | Qwen38官方hyper-GDN-MoE完整block | to do |
| Q38G | P2 | Qwen38官方hyper-QSA-MoE完整block | to do |
| Q38H | P2 | Qwen38官方PLE所在完整block | to do |
| Q38I | P2 | Qwen38含PLE与QSA四层周期组 | to do |
| P00 | P1 | 先建立可达性能上界和实际周期账本 | ongoing |
| P00.1 | P1 | 归档原始计数复算与带宽上界检查器 | done |
| P00.2 | P1 | 当前DUT事件计数与互斥周期桶闭合 | to do |
| P01 | P2 | SiLU重叠Host集成A/B | ongoing |
| P01.1 | P2 | 已归档SiLU组件修复与数值/异常门禁 | done |
| P01.2 | P2 | 完整Host与实际iDMA双层及官方A/B | to do |
| P02 | P2 | Dense权重跨token复用及64beat批处理 | to do |
| P03 | P2 | Attention与GDN调度性能优化 | to do |
| P04 | P2 | 当前完整top的SRAM和800MHz实现检查 | to do |
| R00 | P2 | 六类典型block集中发布 | to do |
| F00 | P3 | 典型block之后接完整模型与llama backend | to do |
| F01 | P3 | MTP状态分支与视觉多模态独立验收 | to do |
| U00 | P0 | 冻结当前三模型合同与回放工作量 | ongoing |
| U00.1 | P0 | 固定0.8B官方配置与dense-FFN几何合同 | done |
| U00.2 | P0 | 完成三模型官方回放与性能工作量冻结 | ongoing |
| U01 | P1 | 三模型典型block数值及90%联合验收 | to do |

部分子项 done 的父项仍为 ongoing；官方权重、真实RTL/状态连续性按各自完整门禁验收。
队列默认跳过所有 done 和已有负责人正在执行的 ongoing 叶项，不自动重开历史任务。

2026-10-12 QKV归约接入进度与资源/验真范围见 [Qwen2分块归约记录](QWEN2_QKV_BLOCK_REDUCTION_20261012_CN.md)。这是Q21.3的实现子门，未关闭Q22/Q23/U01；官方BF16为用户批准目标，原FAIL与其余四个block的M128缺口保留。

2026-10-12 本轮QKV分块归约已在公开21命令cold M16完整模型到达终态，17输出共1,671,168B ACK，15主阶段+6内部节点对固定配方逐bit一致、官方27已分配门通过。Q21.3仍ongoing：M128同源实际链正在执行，future scores未执行不能冒作全29节点通过，Chisel仅前端/默认关闭，尚无本批RTL验收。a2e4远端payload成功；model浅克隆基线FAIL已修且冷117测试通过；frontend原job cancelled但保存了完整PASS工件，等待修正预算后的新CI。详见分块归约记录；五block M128总门保持open。

2026-10-12 15:42 UTC：Qwen2-1.5B L0完整cold M128公开21命令对应软件模型已完成，官方27已分配因果节点门均通过，116源/实际ACK/固定配方经独立复核。[完整记录](QWEN2_QKV_BLOCK_REDUCTION_20261012_CN.md)。Q21.3仍ongoing，保留full29缺口、carried128/Chisel/RTL未验；Q22/Q23及其余四block M128不关闭。新增共享Add的原始事件已记录，完整周期预测待纳入其bank/Vector开销，不声称达到80%利用率。

38b943c 的model/frontend/payload三门及下载工件已闭环：新118模型小测＋原71数值策略小测，159 CHIRRTL，均保持各自身份；未把这些CI小门称为M128重放或RTL数值验收。

2026-10-12 0.8B L0 typed owner前缀：真实embedding→RMS→QKV/Z/AB，两个M128输入窗口8个owner终态及原12项前缀数值门通过。见[来源与范围](QWEN35_GDN_PREFILL_PREFIX_20261012_CN.md)。这仍是S04/Q35B下的模型前置子门，未接公共Command128/Conv/chunk/state/FFN、无新RTL；第二输入窗口不等于carried GDN状态验收。S04/Q35B/U00.2/U01及五block M128总门保持open。

2026-10-12 17:04 UTC：0.8B L0的真实typed投影写回→Conv4/SiLU/history staging已在两个M128输入窗口完成10个owner终态，原12项前缀门、实际Conv/SiLU同输入门及端到端原门通过。见[本轮数据与范围](QWEN35_GDN_PREFILL_CONV_20261012_CN.md)。两个Conv均cold，history未发布/无generation提交，仍不是carried GDN或完整block。S02/S04/Q35B/U00.2/U01及五block总目标保持open。e0bf前缀两CI及其下载工件已核闭环，cb93596的独立产物复核、两CI及下载工件均已闭环。

2026-10-12 17:34 UTC：0.8B L0实际Conv/AB→InputPrep M128软件前缀完成，两个cold输入窗口12个owner、全部1,638,400个新增FP32字对独立固定配方一致，原RMS/投影/Conv门保持。103项冷小测试通过；[数值与范围](QWEN35_GDN_PREFILL_PREP_20261012_CN.md)保留全部native差异，InputPrep native stage未另授门限。尚未真正chunk/state/fence或完整block，原Chisel准备owner仍M1。S02/S04/Q35B/U00.2/U01及五block总目标保持open。

2026-10-12 18:21 UTC：ada0a8a 两CI/103测试/工件闭环。新增全16头、完整128²状态的M16 true chunk64边界模型174.48秒固定算术逐bit通过；纯官方state原门仍1/262144超限，QKV-only反事实将其消除，不能宣称完整GDN通过。原M128合法UF拒绝保留，显式IEEE软件策略默认关闭且未接Chisel控制。16阶段完整typed协调器、双root最终fence、Down真实FP32seed及pointwise排空小门已落地，实际整链待归约修复后验证。[范围与原FAIL](QWEN35_GDN_CHUNK_PREFILL_20261012_CN.md)。此映射M128 Vector约2124万issue，固定4096资源乐观Matrix利用率≤3.168%，非RTL实测；五block M128总门、S02/S04/Q35B/U00.2/U01继续open。

2026-10-12 19:07 UTC：07b9a9b8 两CI、271测试和18,996B紧凑工件已核闭环。下一批将通用两段K512投影真正接入同一GDN完整typed软件协调器，保留BF16物理跨度、原共享Vector Add、普通/seeded切换及双state最后发布。冷完整workflow305测试/21进程通过；实际cold16→carried16仍PENDING，尚不继承独立候选的state通过。[实现与验真范围](QWEN35_GDN_PROJECTION_REDUCTION_20261012_CN.md)。显式IEEE与新投影的Chisel控制/公共Command128仍未接，五block M128总门不关闭。

2026-10-12 19:20 UTC：8ef1239a 两轻CI/305测试/47执行测试源与紧凑工件闭环；0.8B L0同一完整typed软件模型cold16→实际carried16完成32终态、双root generation1→2，所有原已分配完整节点/state/operator门通过，旧FP32状态单点失败已在实际链消除。Prep单独门未分配，Chisel/Command128仍未接，不升级为M128或RTL通过。[逐项记录](QWEN35_GDN_PROJECTION_REDUCTION_20261012_CN.md)。同源完整M128已基于分阶段预算启动一次，S04/Q35B/U00.2/U01及五block总门继续open。

2026-10-12 19:52 UTC：完整cold128已到16阶段终态并提交generation1，原carried128继续。旧normal-only输出比较在两个合法BF16 subnormal处拒绝，原FAIL保留；新增显式finite-prefill比较域接受合法有限编码，保持全部max/mean/ULP/state门和实际算术不变，独立位级/旧域等价门已通过。见[比较域依据](QWEN35_GDN_PROJECTION_REDUCTION_20261012_CN.md)。完整双窗口M128仍待实际终态及全部比较，不关闭五block/Chisel/RTL总门。

2026-10-12 19:57 UTC：0.8B L0完整typed软件模型cold128→实际carried128一次运行正常完成32终态和双root generation1→2；每窗真实两个64-token chunk。finite-BF16域、全部原数值阈值下，各17个已分配节点、完整FP32 state及Conv/SiLU operator门均通过，旧normal-only拒绝明确保留；Prep仍unassigned。313/22最终轻门通过。[完整记录](QWEN35_GDN_PROJECTION_REDUCTION_20261012_CN.md)。这是S04/Q35B的模型数值子门完成，公共Command128/Chisel/RTL仍未接，不关闭父项及五block总验收；下一步0.8B L3 M128模型，35B-A3B两block未完成。

2026-10-12 20:07–20:20 UTC：37b7de的GDN软件/公共payload两CI成功，313测试/22suite及21,490B工件逐hash核验。下一步0.8B L3完整prefill模型的官方BF16 prefix采集源码已准备并独立审查；环境替换后两源码逐hash精确恢复，新环境11项stdlib门通过。旧M16原始采集不可见，旧M128终态未知，不能继承成现环境通过。参考入口和下一数据链范围见[L3计划](QWEN35_L3_PREFILL_MODEL_20261012_CN.md)。0.8B L3/35B-A3B两block及Chisel/RTL总门继续open。

2026-10-12 20:53 UTC：0.8B L3新官方M16/M128采集完成；同一实际typed软件资源执行RMS→packed Q/gate→K→V的cold128/carried128前缀，8个accepted terminals、1,572,864个BF16输出逐bit吻合官方，原门通过。M16元数据路径错误原EXIT1与独立posthoc身份恢复并列保留。见[L3记录](QWEN35_L3_PREFILL_MODEL_20261012_CN.md)。仅四阶段前缀，无实际KV续写、Norm256/RoPE/Attention/FFN和公共Command128/Chisel/RTL；C03.2/C04.2/C05为实现子门，S01/Q35A/U00.2/U01及五block总目标保持open。2b21两轻CI与1116B工件已核闭环，本批模型小门/新CI继续收口。


2026-10-12 21:42 UTC：8ca23b28 三轻CI与L3/GDN工件闭环。0.8B L3实际typed软件八阶段RMS/QKV→Q/K Norm256→partial64 RoPE的cold16/carried16完成16终态，前缀8门及每窗22/57原producer门通过；其余35 producer尚未纳入统一观察（其中4个最终输出已另验），KV/Attention/FFN尚未执行。[范围及预算失败](QWEN35_L3_PREFILL_MODEL_20261012_CN.md)。首轮M128在600秒宿主预算受控停止（cold8＋carried4），不是整链通过；精确检查开销小修后完整双窗重新执行一次，当前PENDING。仅C03.2/C04.2/C05模型子门推进，不关闭S01/Q35A/U00.2/U01或五block总门。


2026-10-12 21:51 UTC：0.8B L3同一typed软件模型cold128/carried128的RMS/QKV→Q/K Norm256→partial64 RoPE八阶段前缀完成16终态，原门及独立raw/source审计通过。新增Q Norm/Q RoPE输出cold4点、carried1点各1ULP差异，最大0.015625，不能称全bitexact；全部原阈值保留。首轮600秒预算FAIL与修复后522秒PASS分别归档，宿主检查加速非硬件优化。最终90 L3＋原316 GDN同源轻门已验，远端CI待闭环。[来源与精确范围](QWEN35_L3_PREFILL_MODEL_20261012_CN.md)。完整L3、公共Command128/Chisel/RTL、35B-A3B两个block及五block总门仍open。


2026-10-12 22:00 UTC：78e2f52三CI与两份compact工件已核闭环（L3 90/10/70源，GDN316/22/49源）。前缀四个/一个Q Norm BF16差异经固定全形状官方QK单算子传播，cold/carried原QK门最大差1.0/0.5失败，cold缩放logits仍0.0625失败；尚未执行实际Matrix owner，不能当硬件失败或放宽验收。先定位mean/rsqrt通用数值差，再接完整L3；前缀PASS与完整block open并列保留。

- 2026-10-12 C2局部进展：旧C1的Norm小差传播为条件QK 10/8个超限已保留；通用DEFAULT256+SqrtDiv修复在真实双M16八命令/22已观察producer零bit差，完整M128前缀待终态。Chisel同模块overlay仅源/符号门，生产Host未启用；完整L3/五block总项仍ongoing。
- 新KV staging仅34项合成控制门，实际K/V与最终block凭据接线todo。固定单Scalar映射的L3条件利用率上界约7.56%/7.77%，不是实测或最终Vector架构结论。
- 后继QK blocker：matching-input的现行ascending FP32 FMA仍cold1/carry2字超限（max1.0），其中carry [0,5,26,64]因果有效；独立C配方预检，尚非Matrix owner。需通用归约机制定位，禁止用C2条件官方QK通过替代此门。
- 22:30 UTC更新：C2真实cold128/carried128八命令前缀16终态完成，22已观察Norm/RoPE producer的FP32/BF16全部逐bit相同；61源/18输出/52观察封存复核。只关闭C2局部前缀数值门，QK配方超限、KV/完整L3/Chisel/五block总项仍open。

- 2026-10-12 23:04 UTC：478a542两CI/137tests/80源工件闭环。显式矩形Matrix profile与旧模式共资源小门完成；GQA同输入双M16子算子实际QK/scale/BF16概率/context全bitexact，FP32softmax过原门。18个owner门含held-success poison修复和M17/cache33边界；干净209tests/18suites通过。该运行重放封存prefix写回，KV装载仍宿主设置，不是现场完整block或M128；57节点/最终fence、公共Host/生产Chisel/RTL和五block总门保持open。[准确范围和来源](QWEN35_L3_PREFILL_MODEL_20261012_CN.md)。

- 2026-10-12 23:28 UTC：97446 的 L3/GDN/payload 成功工件已核，两个旧 Qwen2 门因源身份绑定失败，原 FAIL 保留；新历史 commit:path 与 observer v2 修复48小门通过。实际 Sigmoid gate 双M16回放四官方门逐bit相同、46合成门；GQA封存28门及八旧新全事件对照通过，仅宿主检查优化。冷受影响1392次软件测试执行（原1395人工合计更正，原日志未改）/313秒已过，新CI待验，完整L3活链、M128 GQA/五block/Chisel/RTL仍open。[范围与来源](QWEN35_L3_PREFILL_MODEL_20261012_CN.md)。

- c554后继身份收口：L3 219/19/95源与GDN330/23/50源原CI工件已核；Qwen2 contract旧helper传递pin拒绝保留。六文件显式v2闭包与原frontend全文门精确两行扩展修复完成，独立审查及全新环境完整contract566小测/156.913秒通过；未重跑模型/RTL、未改数值门。原frontend821测试/159 CHIRRTL及工件已成功闭环，c554五門为四成功/一身份FAIL；新修复提交CI待验，19阶段L3活链、真实KV末残差提交与五block总门仍open。


- 2026-10-13：a35adbd7 原四 CI 全成功并核完工件（contract566、GDN330、frontend821／159IR）；原 c554 身份 FAIL 与 5 个未打包 .pyc 的不可比限制保留。完整 L3 19 段 typed 软件活链与真实末 Add→KV 双根提交已接线，小门及独立审查通过，真实双 M16 执行中；原 57 producer 中未物化 mask-add 保持缺失，不能按末输出替代验收。公共 Command128、生产 Chisel／RTL、五 block M128 和 S01/Q35A/U00.2/U01 父项保持 open。[来源与范围](QWEN35_L3_PREFILL_MODEL_20261012_CN.md)。

- 2026-10-13 00:55 UTC：L3 cold16真实19命令完整typed软件链及末Add→KV双根generation1已完成；56实际物化producer、最终输出、实际KV和行和全过原门。mask-add未物化保留，6个融合因果真实小门证明max/exp/sum排除future与PV零系数语义（±0位差保留）。carried16原任务继续，完整双M128、生产Command128／Chisel／RTL和五block总门未关闭。[指标与范围](QWEN35_L3_PREFILL_MODEL_20261012_CN.md)。

- 01:00 UTC：原双M16监督在1200秒软件预算退出，cold19完整/原数值门通过；carry17、Down部分、末Add未到，generation仍1。原FAIL与部分证据已保全；下一完整pair1800秒依实测预算待本批CI后启动，不能继承partial state或关闭双窗门。

- 2026-10-13 01:45 UTC：43fc70f三CI及596测试/两份紧凑工件已核闭环。0.8B L3完整cold16→实际carried16 typed软件链从raw重新运行正常结束，38终态、双root generation2/32tokens、每窗56已物化原producer及最终output/KV/行和全过；91源/42输出/102观察/实际cache依赖独立核验。原1200秒FAIL不覆盖，57中未物化mask-add保留；公共Command128/Chisel/RTL和完整双M128仍open。[完整范围与计数](QWEN35_L3_PREFILL_MODEL_20261012_CN.md)。后续单次7200秒M128预算依据1364秒完整M16和33秒guard计时，非数值门限。
- 用户要求所有已过case补MAC/占空比账：本双M16已有物理流量、Matrix FMA、Scalar/Vector逻辑次数；硬件全周期/busy/stall/overlap仍unknown。条件单Scalar映射Matrix上界3.1026%／3.0891%独立列示，不当实测。Qwen2 M128、L0 M16/M128与L3子链现有证据清单继续补齐；后续流水整改必须计bank端口/lease/排空和完整周期，不关闭U01或承诺80%。
- 2026-10-13 已完成首批15个已有结果窗口的[MAC/占空比证据清单](PASSED_CASE_UTILIZATION_20261013_CN.md)：逐case区分软件调用/源界/RTL实测及数值通过范围，缺完整周期或busy timeline明确unknown。98c7历史L3双M1有实测0.14426%／0.14413%和发射占空比2.37385%／2.37148%，保留压力DDR和native未验范围；其余软件case不由宿主秒数计算利用率。流水机会与bank/lease/credit/异常排空代价已列，完整计数器无扰接入和当前五block联合验收仍todo。

- 2026-10-13 03:46 UTC：0.8B L3完整cold128→真实carried128 typed软件链一次运行EXIT0，6658.907秒在7200秒预算内；38真实终态、KV0→128→256、generation0→1→2。每窗56已计算producer与最终output/KV/行和原门均通过，KV逐bit相同，mask-add未物化保留；91源/42输出/102观察与真正carried依赖另有独立审查。见[完整数值与来源](QWEN35_L3_PREFILL_MODEL_20261012_CN.md)。仅关闭该完整M128软件子门；公共Command128/生产Chisel/RTL及五block联合总门继续open。当前已有Qwen2 L0 coldM128、0.8B L0/L3双M128的已分配软件数值门；35B-A3B L0/L3完整block尚未实现验收。
- 本次双M128 Matrix实际软件FMA为2,415,919,104／2,483,027,968，Scalar请求7,989,248／8,644,608；完整硬件cycle/busy仍unknown。单Scalar基本请求条件Matrix上界≤3.0661%／≤2.9692%，未满足80%/90%目标；17条逐窗口[性能记录](PASSED_CASE_UTILIZATION_20261013_CN.md)保留证据层级。下一步优先资源安全K2048、官方精度与真实35B prefill接线，任何流水整改仍须固定资源、bank/lease和原数值门。

- 2026-10-13 35B前置：K2048使用原16×1376×256 A SRAM的双N160显式destructive lease，保持五context；原Matrix/Vector/TypedMemory实际两partial→Add→BF16写ACK小闭包已接线，旧0.8B默认路径保持。合成K2048、N160、跨窗、混模式、错误退休/reset门推进，官方35B profile与完整block未验。详见[资源、实际范围与下一步](QWEN35_35B_K2048_PARTIAL_LEASE_20261013_CN.md)。硬件全cycle/busy仍unknown；源/CI小批收口中，不关闭Q35C/Q35D/U00.2/U01。

- 2026-10-13 05:15 UTC：f8a46ff的K2048双partial四轻CI/387+247测试及工件全部核验闭环。新增35B原始embedding→H2048 RMS实际typed-memory子链在同资源先M16再M128完成全ACK/终态发布；全部对应FP32节点/BF16输出对冻结原官方组件逐bit相同。三块1024 BF16存储不扩容，以output前128B保存32FP32 partial并二次读输入。M128实际1,332,736 Scalar请求、1,572,864B读、524,288B写ACK；硬件cycle/占空比仍unknown。见[来源、资源和范围](QWEN35_35B_H2048_RMS_20261013_CN.md)。本批独立review及冷447+247门已通过，远端CI待提交后核验；35B完整两block、生产Chisel/RTL、Q35C/Q35D/U00.2/U01仍open。
