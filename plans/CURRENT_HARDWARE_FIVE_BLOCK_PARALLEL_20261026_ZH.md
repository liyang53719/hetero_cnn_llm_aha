# 五类 block：原始 Chisel 完整 M128 数值后再 RTL 回放（2026-10-26）

## 2026-10-31 03:25 UTC：FULL执行模式源码接通，真实预算/宿主仍阻塞（TEMP / INCOMPLETE）
- 实际run41163215771在原AVX512门早期拒绝，未runtime/build/DUT，没有可填full预算的速度证据。共同硬件不要求宿主CPU ISA相同，但原参考/ABI门不能无验证替换；合规固定云环境待用户/资源路径解决，不随机重抽runner、不降门。
- 新Python模式已接原prepare→flow→numeric_tail→consumer→原逐块严格验收→safe summary。FULL必须显式独立已审五份wall/maxcycles及实际calibration/review pin；接受SHA保持None、模板全null/ready=false，不能直接启动。calibration仍原300秒×5；FULL不继承无条件300/20000，也不把timeout当完成。
- 内层consumer保持原execute/Popen/清理AST及1/2返回；外层全5同artifact严格PASS才FULL transport0，明确exact mismatch为1，timeout/未到输出/缺state/缺profile为2。summary核固定根binding、源码pin、预算admission、每report实际mode/effective limits，再逐receipt重聚合，不能换label迁移cal结果。
- Chisel/C++/硬件/数据/参考/舍入/ABI字节未改；原冷M128 chunk路径保留。新增Python源码身份仍需未来同新source一次共同build，不能借未产生的旧binary。当前仍是Chisel发射IR/SV模拟，不是冻结后独立最终RTL；五块完整M128和最终RTL均0/5。
- 原21000秒及资源caps不增，现非DUT预留18000秒，五full窗口至多合计3000秒并须满足实际剩余首步时钟，未保证能完成。完整block周期/速度/比较耗时依据未有，利用率仍UNMEASURED；预算填值与实际启动留待真实证据，不继续空转资格任务。

## 2026-10-31 02:55 UTC：已审 SV 观测基线接回原五块生产链（TEMP / 待真实校准）
- 以 d339 实际证据提交为基线合入原隔离 production 候选：不覆盖新扫描器/投影器；旧 canonical/C7/85口历史原样保留。实际 run41159843264 proof f88769ed…及独审598ff33f…、summary dfacbbe2…被门逐文件固定哈希读取。ready 只表示限定观测 SV 基线已审，可继续原后端构建，不授予数值或最终RTL通过。
- 为避免300秒仅有reset样本，本包经授权仅调整driver只读日志调度：首个while成功step立即running，后每64 activecycles检查steadyclock且至少1秒才再输出；原DUT step/while条件/算术/ABI不改。safe summary复用原Popen/outer cleanup，输出有限进度及事后日志hash，未绑定/无active则null；外层elapsed除速率非即时仿真率，SIGKILL不保证最终帧，正式C++编译仍待同一次build。
- 原主链不重设计：35B runtime先装并严格清理→单次共同build→其余runtime→owner/weights/5份独立参考→五块M128同刺激。同一4096 MAC固定硬件/122口/新SVhash ec70…；下一fresh host重新检查Python3.12/x86_64/AVX512f以运行全5，不迁移旧host或16-lane结果。源码资格与真实archive/link/GCC双头依赖/运行资格分开。
- 当前实际入口仍只有每块300秒BOUNDED_CALIBRATION，21000秒总限及19500秒预留不变，不是完整执行mode。校准需导出原driver已有HOST_PROGRESS的实际周期/调度/速率证据；无完整block总周期依据时明确unknown，不把部分区间利用率当4096资源完整block分母。FULL_BLOCK_ACCEPTANCE模式尚待实际校准预算证据后最小接入，不能无限重复资格壳。
- 当前后端会发射IR/SV并编译仿真，属于原Chisel生成模型的数值执行链，不是纯Python/Scala行为模型，也不是冻结后的独立最终RTL回放。完整五块M128数值仍0/5，最终同刺激RTL仍0/5。源码提交不包含activation实体；实际执行待独审、CI、资源及冲突检查。

## 2026-10-31 02:48 UTC：真实两模块61-bit限定SV差异证明 PASS（非数值）
- 实际run41159843264成功，source c312f2ee、launch b845ae54；两原样安全回执及独审见 candidates/observer_sv_only_20261030/evidence/run41159843264/。15阶段严格native0、errors0、cleanup/EOF/gzip均真。
- 旧/新全SV normalized6555ede3…/ec70f911…与既有身份相符。Router仅8端口/4直接assign、Dense仅4端口/4直接assign新增四字段61-bit；删除规定增量后实际剩余normalized bytes分别179237/44477654双流逐字节相等。92模块顺序不变，82未变+8既定observer修改+2本次限定证明，无额外模块变化。
- 这是完整实际SV窄差异证明，不再仅toy/源码推断；仍不声称一般逻辑等价、五块数值或RTL回放通过。此前三次失败历史保留，不倒改为PASS。生产门接入需独立复核，本证据不自动re-pin。
- 原180秒scanner/300秒projection及3小时总cap未增加；未跑Verilator/GCC/archive/link/数值。五块完整128-token数值及最终RTL仍0/5，接下来回到同一统一4096硬件的五块主线。

## 2026-10-31 02:18 UTC：官方实例FileInfo布局修复（TEMP / SOURCE-ONLY）
- 实际run41156443649终态FAIL，前14阶段严格完成，projection75.173秒/native1。已取得真实有限拒绝：old / TransposedDenseDownOwner / PROJECT_MODULE / REJECT_NEW_KEY_REMAINS_IN_UNPROJECTED_LOGIC_PORT；旧Dense归一化hash e07f04…与两边whole/canonical本次真实绑定相符。471600行/44477644偏移是旧诊断EOF残留，不可当真正拒绝位置。
- 官方同布局小AST仅把WDefInstance NoInfo改为FileInfo，实际emitter在banks实例首行产生SourceInfo尾注释，使旧START正则不匹配，复现old/new Dense误拒。此是可复现解析缺陷，不是声称已读取本次真实SV实例行或确证唯一根因。279源端口上界小于4096，不扩cap。
- 修复只额外识别原b49c SOURCEINFO.fullmatch认可的首行尾注释，所有注释/实例字节原样保留；fixed实例/4个标签offset/精确表达式及全部剩余字节比较不变。任意注释/pragma/伪SourceInfo仍拒。官方小fixture最终旧新残余bytes直接相等，不继承完整SV通过。
- 有限诊断新增classifier分支/5计数及饱和标记；最终未豁免标识现在记录真正occurrence offset/line和有限类别，无raw token/body/log。原reason仍保留，失败不授权re-pin。
- 原15stage、180秒scanner、300秒projection、10800秒whole及所有硬件/删除判据不变。源码提交不运行重job；新fileinfo唯一nonce待sourceCI与冲突检查后单独激活，前三nonce不复用。
- 五块128-token完整数值及最终RTL仍0/5；真实SV证明未通过，不能由toy或CI绿灯更新生产基线。


## 2026-10-31 01:37 UTC：实例命名端口标签误拒修复（TEMP / SOURCE-ONLY）
- 实际scanfix run41153553582终态FAIL：前14阶段严格成功，旧/新SV扫描42.023/36.121秒；最终projection35.040秒/native1、supervisor errors空、清理EOFgzip完整。非cap超时；child拒绝谓词当时未导出，具体真实原因仍未知。不能把toy复现当实际失败原因确证。
- 官方FIRRTL DefInstance小AST复现原projector错误：既有child命名port标签被当parent同名信号，Dense旧/新都误拒。严格exact TransposedDownDenseBanks banks实例分类仅豁免4标签offset，不删除/重写其字节；真实连接表达式、member/hierarchical、其它实例/类型、条件程序或未知语法仍拒。原四field删除规则与全部剩余normalized bytes逐字节比较不变。
- 最终候选在官方exact实例toy经原scanner归一、旧新残余bytes直接比较相同；普通reg/memory toy排除了部分猜测。不继承真实SV通过；源码测试精确范围见发布manifest。
- 失败诊断保留有限reason/phase/module/side/计数/哈希，未知为null，超界有饱和标记；无SV/body/token/rawlog。失败native1永不授权re-pin，严格导出将exporter独立输入证据与child已观测区分。
- 原15阶段、scanner180秒、projection300秒、whole10800秒不增；无Verilator/GCC/archive/link/weights/DUT。源码提交不启动；新portlabel唯一nonce待独审、source CI与无并发确认后激活，旧launch不复用。
- 完整五块128-token数值仍0/5，最终RTL回放仍0/5；只有真正完整SV差异证明核验后才能审后续production门，不能由CI绿色自动re-pin。


## 2026-10-31 01:00 UTC：SV专项扫描失败修复（TEMP / SOURCE-ONLY，未重新实测）
- 用户已明确批准本次最多3小时的SV专项；原run41151061202终态FAIL，前7阶段native0/严格完成，old_svscan 182.287秒、native_exit=null、error_count1，清理/EOF/gzip完成；与180秒限时一致，但未保存错误类型，具体原因仍未知。新版与投影未开始，禁止继承PASS。
- 单遍修复仍调用原b49c scanner：完整LF终止模块的原digest同时更新module/whole hash，严格连续覆盖与终态code证明；不改scanner字节、旧新canonical/SV期望、61-bit投影判据、硬件或预算。合成34,998,998B/96模块实测旧18.012秒→新9.236秒、全部元数据相等；仅合成性能，不是实际92模块证明。
- 安全摘要V2区分expected/observed，失败observed=null；错误只输出固定枚举和CPU观测，不泄露日志原文。source轻测通过范围以本次发布manifest为准，不代表真实SV接受。
- 原launch已消费；新唯一scanfix nonce只可在修复source CI成功、无活动重任务与直接parent/single-A校验后启动一次。源码提交本身不启动。原15stage caps与whole10800秒不变；无Verilator/GCC/archive/link/weights/DUT。
- 主线五块128-token完整数值仍0/5，最终RTL回放未通过；SV接受/生产re-pin继续阻塞于实际两边whole/module哈希与严格字节投影结果。1024/1224未澄清不阻塞128。


## 2026-10-30 — SV-only 严格差异取证候选：TEMP / SOURCE-ONLY，未激活

- **DONE（仅源码/轻测）**：独立fresh CI旧/新完整155源码、各7helper、既有完整original IR→canonical→emit SV→scan→两模块严格差异证明入口。专用source pins 664项，SHA256 `7e7681939364073d9d236d51b06608fbf2bc90f9cf36a8256f6340ef545e2413`；normal/-O各53项轻量测试通过，含真实project_proof合成链及失败双artifact出口。它们不是实际全SV证明或数值通过。
- **ONGOING / TEMP**：保持旧/新canonical `90464ff…` / `00897fd…` 和whole normalized `6555ede…` / `ec70f91…` 硬锁；只审核两额外模块的61-bit key四字段端口及直接转发，其他normalized字节须严格一致。无自动re-pin，后续真实证明仍需独审；当前全SV整体re-pin继续暂缓。
- **TODO**：先核新source远端及CI，再另一个仅新增唯一launch的direct-parent提交激活一次；本源码提交不触发。原class不搬、本地未知owner84990不触碰/重试。仅JDK/JAR和SV-only，不含serialVerilator/GCC/providers/archive/link/weights/reference/DUT。
- 15阶段wall6360s+cleanup450s+parent900s=内部7710s；GitHub step129min=7740s只取整30s，workflow保守9060s，whole10800s余1740s。原phasecaps最大RSS6GiB、freshhost至少7GiB；保留原bootstrap更紧AS/log caps及whole repo+work的100k entry总边界。
- 只导出两份各≤64KiB的proof/summary及固定字段runtime身份hash，不导出rawSV/IR/classes/o/log/weights。CPU/runtime及最终数值资格不由此继承。五块M128完整数值仍0/5，最终冻结同RTL回放0/5，利用率未测。既有实际frontend/122 ABI/单TU限定证据及下方历史正文完整保留。


## 2026-10-30 20:34 — 实际 frontend/ABI/单 TU 限定资格通过；SV re-pin TEMP 暂缓

- source `a06b51416090fce2ad3d04336c82a5b7a2d00b97`，launch `50f2e807f28f11e80ffc418461da94fe1ba3c80b`，run `41118989254` SUCCESS；24阶段严格终态/cleanup/EOF/gzip/native0，完整4096 MAC不变。证据：`candidates/observer_frontend_qualification_20261030/evidence/run41118989254/`。
- **DONE（精确范围）**：实际 frontend、122-port header ABI（旧85不变+37观察输出）与真实 GCC 单 driver TU ET_REL / `.d` 依赖资格；不是 archive/link、DUT 或数值通过。host frontend 382.55016183s / RSS9596760064 B；driver TU 9.280295733s / RSS282021888 B。CPU avx512f=true只观察，runtime_qualified=false。
- **ONGOING / TEMP**：92 SV模块82 normalized相同、10改变，含额外 `Public21QkvReductionRouter` / `TransposedDenseDownOwner`。61-bit key / SourceInfo路径仅候选解释；尚缺绑定实际旧新hash的严格差异证明，整体SV re-pin不批准，旧production门保留。原metadata继续OBSERVED_UNREVIEWED，审计acceptance_authorized=false。
- **TODO**：先完成最小SV-only proof方案与独审，再决定正式生产全五块执行；未启动新job，不重复完整frontend。五块128-token完整数值仍0/5，最终同冻结RTL回放0/5，利用率未测。维持4096资源/同硬件、舍入/路由契约和原预算；不继承旧16-lane PASS或拿IR替RTL数值。
- 本包5项normal/-O测试仅合成审计资格；真实结果另由原2JSON及644闭包复核。只发布有界metadata/pins/脚本，不上传rawSV/IR/classes/o/rawlogs/weights。


## 2026-10-30 19:50 frontend-only / 真实单 driver TU 接线（TEMP，尚未 activation）

- DONE / SOURCE：基于d5cc9ff7501c9b99eeb17b03df20006604341bc7，将已实测IR的canonical/122口证据用于独立frontend-only候选。旧baseline原件保留；沿原155源8观察覆盖、完整4096 MAC、同一五profile硬件定义，不按模型重elaboration。16文件源码包manifest SHA446706d8244debedecf1d196dade84fcd47906f1804619f106b62ffa299995e8；专用644 pins SHA99adde3413b505b67ee68939e992f6e11eb50274662a1042417ce8121b5797c8。详见[候选范围与预算](../candidates/observer_frontend_qualification_20261030/README.zh.md)。
- PASS精确范围：21项core＋14项wrapper/export＝35项normal/-O轻测，YAML/bash语法通过，均source/synthetic；不证明实际frontend或driver编译。两个变更Scala helper＋五个纯AST依赖实际小编译native0：14.637411039秒、观测RSS272748544 B，strictcleanup/EOF/gzip完整，原RSS1GiB/CPU60/wall90限内。本次小编译没有编译155源、elaboration、生成SV或运行数值；[受控证据](../candidates/ci_frontend_pipeline_r2_20261029/OBSERVER_HELPER_COMPILE_20261030.json) SHAaeb84b01d7dd2c1a48fd446a08e7bff5337b8c8f9773cef22f0c683d03185a55。
- ONGOING / TEMP：候选只允许原HIGH→精确canonical与原变换→SV及完整normalized/module-fingerprint观察→串行Verilator frontend→真实header完整122口对照→Make严格语法和真实单GCC driver TU .o/.d。depfile必须来自实际-MMD且含两个观察header和sparse header；ET_REL对象不是host binary。明确不做archive/link、权重、reference、DUT或数值运行；新SV身份仍OBSERVED_UNREVIEWED，不能自动重pin接受。
- 预算逐层绑定同一首步monotonic起点：whole job21000秒；inner12000（16 stage wall11100＋cleanup480，余420）；prep预约2880但原aggregate1800更紧动态截止仍保持；3个parent metadata共900，执行step15780秒，含clock/checkout/guard/export/upload的声明envelope17100，whole job余3900。动态剩余不足即拒绝，不承诺各阶段最坏值都可用满；原supervisor/caps不放宽，资源不足不缩硬件。
- 发布只含两个白名单metadata文件，总≤2MiB（summary≤64KiB、qualification≤2MiB−64KiB），包含必要真实Make/dep文本及严格来源，不上传IR/SV/class/object/ELF/rawlog/系统header库存/权重。P0 avx512f仅原exact-token能力布尔观察，不承诺runtime/参考CPU资格，不改变profile策略。
- TODO：源码与CI/交叉审查确认后，另作唯一source→单文件activation（observer_fixed4096_frontend_make_driver_20261030_once），目前没有新重型运行。实际SV/ABI/Make/.d需再次独审才能推进共同backend及完整数值；原IR成功不迁移成frontend通过。五块128-token完整Chisel数值仍0/5、最终冻结同刺激RTL0/5、有效MAC利用率未实测，80%/90%目标保持，无本轮数据清理。


## 2026-10-30 19:37 实际HIGH/LOW描述符与8源差异审计（PASS仅限IR结构，数值仍INCOMPLETE）

- DONE / 实际IR：run41114764250，source975556/launch ec198，九阶段native0/error0/complete。统一155源8覆盖完整编译134.383487633秒、原HIGH/official LOW210.570589043秒、descriptor29.056340970秒；原严格cleanup/EOF完成条件保留，不继承旧run结果。原四份bounded metadata见[本次证据](../candidates/observer_ir_only_20261030/evidence/run41114764250/README.zh.md)。
- DONE / 独立源码与差异审计：1056模块顺序/集合相同，精确8个预期观察相关模块变化、1048项canonical hash不变。实际LOW122口，旧85口name/direction/type/width不变，新增37只读output（27/689bits＋10/259bits）。源码仅观察直连和互斥assert，无原ready/算术/状态反馈；不是整体电路语义相同，也不是generated header通过。
- DONE / annotations事实：实际9022条（9021 DontTouch＋1 TargetDir），旧8985内容与相对顺序保留，增37Top观察target。已pin历史文本重构1358737B的raw/ordered双hash与本次实际run一致；partial旧V1仅文本来源，不继承终态。发布重构脚本、pins及摘要，不上传annotation正文/IR/class。4项synthetic审计测试normal/-O只验证拒绝，acceptance_authorized始终false；限定GO来自真实metadata和源码审计。
- ONGOING：独立新canonical/LOW基线可引用本次observed-canonical.tsv（SHA00897fd49e82036e04195ef6fe2a671e0a3fd948d968de3e47c4dfa7388f6b5c），旧baseline原件保留。当前原metadata的canonical_pass=false/OBSERVED_UNREVIEWED保持，后续必须显式完成新严格接受gate，不能自动repin任意输出。
- TODO：新SV normalized/module fingerprints、实际Verilator header/GCC依赖、新共享backend数值仍未验证；当前ad299只是完整执行链source/mock接线。五块M128 Chisel完整数值0/5、最终冻结同刺激RTL0/5，固定4096 MAC与同一硬件/RTL要求不变，有效MAC利用率尚无实测。本轮未删除临时数据。

## 2026-10-30 19:25 五块 M128 真实消费者与运行来源链整合（TEMP / INCOMPLETE，未数值 activation）

- DONE / SOURCE：将已发布 P0 SRAM gate/up 和 MoE 实际 selector 输入/输出观察源码、统一155源的精确8项覆盖、R2 driver/headers及只读官方参考观察器接入实际 execution closure。真实调用仍为 numeric_tail → provider.prepare → connect_owned → consumer_owned，不是停在祖先run_compare或独立资格外壳。所有五profile共用硬件定义与后端来源，原4096 MAC、FP32/BF16顺序、原PyTorch路由不改。
- DONE / SOURCE：必要完整128输出/cache/state及已定观察逐项判定，缺项INCOMPLETE、精确参考不符FAIL_EXACT_REFERENCE；consumer不提前声称其外层进程已经清理，dut_evidence以真实owner/group absence/EOF收据复核后再给单块资格。numeric_tail/flow/safe summary重验同一来源与五块聚合，eligible4不能冒五块通过。MoE raw FP32与Torch差异只诊断，内部同ID位传递另验，不新增容差或擅认小ID tie。
- DONE / SOURCE：P0来源合同只同步实际改变的6项源/driver身份，原输入/view/程序及20→18真实DDR观察修正语义保留；旧UNOBSERVED metadata不伪造新SRAM receipt。producer/consumer必须核实际GCC depfile中的两个唯一观测header、真实路径与审核SHA，不能仅凭自报已编译字段。
- DONE / SOURCE：35B runtime提前安装，通过原strict cleanup后回调一次原build，再装其余eligible runtime，之后owner/weights/reference/tail；原资源cap、monotonic总期限与预约保持，不把安装当Torch/model import资格。所有新顺序仍仅source/mock验证，原35B历史失败原因UNKNOWN。
- PASS精确范围：82项normal/-O轻测（51验收与完整尺寸mock接线、9独立safe-summary反例、14安装顺序/预算mock、8闭包/来源链）。629项完整source pins精确校验。mock字段不计入真实五块数值结果，源级测试不等于实际IR/ABI、runtime或硬件通过。
- ONGOING / INCOMPLETE：IR-only source975556 / activationec198 / run41114764250已按独立身份启动，真实canonical描述符、完整122端口及其审核仍待原run产物；新SV normalized/module identity、真实Verilator ABI和数值执行尚未完成。旧canonical/85口/SV接受锁未删除或随意替换，本整合批不提供新的数值activation，不影响该IR run的冻结源码。
- TODO：消费并独审真实IR descriptor，再以新产物资格更新严格canonical/ABI/SV链；完成同源新五块128-token数值后冻结输入/参考/配置与源码，再同刺激最终RTL回放。当前仍300秒BOUNDED_CALIBRATION运输模式，未冒FULL_BLOCK_ACCEPTANCE；后者完整预算待实测校准。
- 五块完整Chisel数值仍0/5、最终冻结RTL0/5，利用率未实测；80%/90%目标保持。临时文件清单复查，本轮无数据删除，不上传权重/NPZ、IR/class、原日志或唯一运行证据。整合细节见 [源码接入状态](../candidates/same_job_execution_20261030/OBSERVER_INTEGRATION_STATUS_ZH.md)。


## 2026-10-30 19:18 补齐后续真实锁所需 canonical / 完整端口证据（TEMP，未 activation）

- DONE / SOURCE：发现IR-only原先只导出hash/count，后续actual backend仍缺新canonical完整manifest，故18828不先激活，先补同一IR的只读描述符，避免再做一遍重IR。新helper直接调用未修改CanonicalHighGate公开semantic方法；只剥Info/TargetDir，顺序不改，实际module/annotation计数。HIGH/annotations exact roundtrip；无新硬件elaboration。
- DONE / SOURCE：原helper实际LOW-port提取经hash/marker绑定后用官方Parser读完整name/direction/type/width，85旧口逐一保持＋37审核只读观察输出；输入在descriptor前后及导出前复核。完整canonical.tsv与details/provenance为≤512KiB独立白名单metadata artifact，不截断为只有digest，也不上传IR/class/rawlog。所有资格仍OBSERVED_UNREVIEWED，canonical_pass=false。
- PASS精确范围：56项Python轻测normal/-O；两helper＋一个微型fixture driver真实编译7.608秒/RSS248766464B，3口官方Parser fixture1.763秒/RSS110387200B，均native0/strictcleanup/EOF。只是本地Debian Java源码/API微测，不是CI工具链、122口、完整IR或数值通过。
- ONGOING：新helper_compile/descriptor各沿既有300秒/3GiB/heap2GiB上限，9阶段wall3180＋cleanup285=3465，3600总预算留135秒；原监督与IR资源caps不变。源提交/CI/独审后才可用未消费r3路径另行activation，未重试原任务。下一步真实descriptor独审后接通新canonical/SV/ABI锁，不直接更新旧接受hash来冒通过。
- 五块仍完整M128、固定4096 MAC/同一硬件与生成RTL哈希；Chisel完整数值0/5、最终冻结RTL0/5，利用率未实测。P0精度合同与MoE原路由基线保持，未批准tie不视为已批准。无本轮临时数据删除。

## 2026-10-30 19:07 IR 目录计数范围修复（TEMP，源码未 activation）

- DONE / PASS（仅真实编译）：run41108031789 / source0719 / launch400a 六阶段均native0，新R2统一155源8覆盖完整Scala编译75.941635151秒、观测RSS1585991680 B。source guard41107649508与launch guard41108031875成功；实际IR运行失败，不能用guard成功替代。证据见[原受控摘要与归因](../candidates/observer_ir_only_20261030/evidence/run41108031789/README.zh.md)。
- FAIL / INCOMPLETE：original_ir 在execute之前因entry准入被拒，HIGH/LOW未开始。已计数19993项＋预留8项>20000即中止，不是完整目录总数。当前扫描仓库＋work，却沿用旧局部IR 20k门；修复显式对齐入口既有aggregate 100k条目门。根范围、预留8项、原supervisor/cleanup及CPU/RSS/wall/tree/file/log预算不变，不保证新准入必过。
- DONE / PASS（仅源码轻测）：新admission有限枚举摘要保留拒绝/不完整census/execute未调用的区别，44项normal与-O分别通过。专用618项闭包SHA256 1277341d821c7ed915b15e4c500d88c6696dab23ff62a923137421b92265e0af；active598未变。新唯一r3路径/nonce及guard/workflow同步，旧17路径保留并拒绝重用，本提交无activation。
- ONGOING / TEMP：先核源码提交与CI，再独立提交一次性activation，获取新R2真实HIGH/official LOW与接口证据。当前122口只是预期；原本地84990未知owner与唯一证据保留，不推断已停止，不触碰它。CI旧classes随job结束未作为可下载payload保留，下一新身份只能按pins重建，不能从摘要伪造复用。
- TODO：把真实P0 gate/up、MoE输入/实际选择输出、独立参考与原实际consumer接入同一执行闭包；完整输出/cache/state及必要观察逐项判定，不能以固定INCOMPLETE壳或子集绿色代替验收。新接受条件仍待源码实现/独审，原路由基线、未批准同分契约、精度/舍入规则不变。
- 五块P0 Qwen2-1.5B、P1/P2 Qwen3.5-0.8B L0/L3、P3/P4 Qwen3.5-35B-A3B L0/L3完整128-token Chisel数值仍0/5，最终同刺激冻结RTL回放0/5，有效MAC利用率未实测。固定4096 MAC与同一硬件/RTL哈希要求、80%/90%目标不变。临时文件清单已复查，本轮未删除数据；原始log/IR/class/权重不上传。

## 2026-10-30 18:30 原始 Chisel 观察接口的独立 IR-only 源码（TEMP，尚未激活）

- 新增独立入口，复用原监督/cleanup/lossless log、固定工具/JAR与原Diagnose空参数，只到统一155源8覆盖的完整compile和HIGH/official LOW，不进入SV/Verilator frontend/native backend/weights/reference/DUT。Verilator只准备原identity所需固定包，避免更改原fresh_host合同。此步骤补新接口证据，不替代完整M128数值链。
- 专用616项闭包以215f active598为底，仅增加8已发布统一观察源和10入口/workflow，逐bytes/hash独立核验；32轻测normal/-O通过，原supervisor字节未改。preflight在execute前一次只读census，超原cap/不可读不调用execute，预留8项；非原子，不宣称运行期连续上界。
- 总预算3600秒、阶段wall2580+cleanup225秒；IR RSS5GiB/480秒/CPU420、tree1GiB/file384MiB/log8/raw16MiB/entries20k保持。目标runner准入未实测，不预先PASS；不会因为全tree API观测不可用而放宽cap。唯一上传typed摘要，不上传IR/class/rawlog/权重/tensor。
- 共享exclusive组避免与原数值bootstrap并发争资源；unique guard要求后续单独activation、单parent/attempt1/source直接parent。本源码提交无activation，无旧run重试。215f source CI41106619735已success，dedup/CPU修复只source/mock资格。
- 新R2的122口只是预期，须实际发射后独立核验；旧local84990未知不迁移PASS，不触碰旧owner。完整五块M128 Chisel/最终RTL仍各0/5，利用率未实测，4096/80%/90%目标不变。


## 2026-10-30 18:21 可选去重权限失败与 runtime CPU 门修复（TEMP，未新启动数值）

- 本轮明确终态：run41096005966/source7bb/launchfd947在17:58:24退出1；原27个backend阶段全部native0、wall合计2985.197s，fresh-host native0/192pins，host_link已完成，共享ELF139950896B/SHA ce0bcb621646cb9286c4273d9cb819e42f1513a4b3084d0b7c76bd44ba83837c。仅build准备，不是DUT执行或最终RTL数值通过。随后optional dedup初始writer census的fd.stat权限错误，在任何artifact修改前退出；runtime安装/reference/DUT均未开始。原job日志和受控summary保留，旧35B安装失败原因仍UNKNOWN，不混作本轮原因。
- 修复：初始/首prelink扫描不可用只NO_OP，保留两份物料、零link、节省0，不假称writers absent；交易开始后扫描错误沿原rollback/recovery并继续抛错，不能伪称零修改成功。实际writer/hash/admission和未知错误不吞掉；safe summary拒绝COMPLETE+UNAVAILABLE等矛盾。36项mock普通/-O独立复测通过，没有读取受限FD、提权或改系统安全/资源设置。保留双份仍受原资源caps。
- 另修静态潜在门槛不一致：runtime_phase原本对全部runtime无条件要求AVX512，尽管外层已选Qwen35-only。现在仅qwen2保留原AVX512 exact-token gate，未知key与错误Python/架构仍拒绝；两个Qwen35原DEFAULT/thread1/taskset/offline wrapper字节不变。10项mock普通/-O独立复测通过，未安装/import，非真实nonAVX主机资格，也不是本轮失败归因。P0原合同不放宽。
- 合并后46项mock测试在normal/-O各通过，未触发实际proc扫描/安装/import。
- 本批仅源码及598项精确闭包更新，无新activation，不改算术、精度、同分参考或固定4096资源。候选R2观察接口仍未完整编译/发射。独立IR-only前置资源census正在审查，原supervisor不改，新的有界尝试需单独source/identity。
- 后续降低重复build成本的方案：原安装可前移并复用同一树，但install不等于Torch/model import；原budget/reservation需重排，两个旧Qwen35树约74.7k entries会纳入build的100k限制，必须实际准入，未静默扩大cap/改flow/新增probe。
- 完整五块M128 Chisel/最终RTL仍各0/5，有效MAC利用率未实测。16afe源码保护CI41103075571已成功。原本地IR84990 owner未知证据保留，不据此说停止或重跑；本批未删除临时数据。


## 2026-10-30 18时：真实 selector 输出与完整消费者接线（R2，TEMP / INCOMPLETE）

- DONE（源码/轻测）：除每token256项真实selector输入概率，新增8项真实 selection.out.fire score/index/rank/last；kind区分事件，feed/read状态互斥，无新ready/算术/调度反馈。collector直接写真实输出score和ID两份4096B文件，绝不以input[ID]回填。新259bits/10信号、Top122口仅源码预期；本版Numeric尚未完整编译或发射IR，不继承V1编译/112口/旧119预期资格。
- 修复采集语义：旧候选把input-link/排序数值检查当落盘前提，会丢失错误样本，已撤回旧collector GO。当前任意FP32位型（NaN/Inf/负数/±0/>1）均原样保存；数值异常只计数，协议/fault/覆盖才阻断。C++真实collector→Python reader合成negative证明错误bits保留，分别观察3个内部差异、6个全概率参考差异、8个selected参考差异；这不是硬件执行。
- actual consumer以active7bb原00bac基线合并P0 resident gate/up与MoE input/actual output/独立reference比较，保留原ffb1合同、host/ABI/pins/cleanup/calibration及INCOMPLETE/exit2。内外比较分开：hardware output vs hardware input[actualID]是内部一致性；同次官方概率及原官方ID形成独立软件参考。无clip/舍入修补/新容差或tie批准。P0旧consumer不能覆盖active更新。
- 官方观察器实际gate-only fixture一次native0：9.347591102s、direct-child RSS354574336B、native前后12项核验，原tuple/local身份与logits/IDs/weights逐bits不变。仅合成输入/权重的固定官方gate，不是完整block/reference；cleanup只按原reference supervisor finally stop/killpg/wait及postverify，不升级strict IR终结证明。
- 包装复建7个base/result SHA在normal/-O分别通过，existing-output/base/result/P0-header负例均拒绝；38项包内轻测加7项observer轻测通过。materialize准入采用显式检查，避免-O跳过。5份旧摘要/patch/test按原字节归档legacy_r1，Git普通移动保留c639历史，不删除运行输入/唯一证据。
- ONGOING：原run41096005966仍source7bb/launchfd947，17:57 API仍in_progress；本次不改其active pins、不增加activation。c639 source guard41100401245成功。新观察候选执行闭包、真实完整reference/DUT、全required-stage比较仍待接通；独立短CI仅compile+原HIGH/LOW的源码方案正审，未激活，不跑SV/RTL调数值。
- 旧本地IR84990缺终结证据且跨namespace owner未知，保留INCOMPLETE、不重跑、不kill。完整五块M128 Chisel/最终RTL仍各0/5，有效MAC利用率未实测；4096固定资源与80%/90%目标不变。


## 2026-10-30 17:36 联合真实 MoE 概率观察候选（TEMP / INCOMPLETE）

- DONE（源码/编译范围）：沿原 Numeric → Pipeline → RuntimeExpertLoop → Top 新增真实 selection.in.fire 的 FP32 softmax 后、topk 前概率只读 Valid tap，保留 P0 resident SRAM 观察，无 ready/算术/路由/调度反馈。每 P3/P4 全128×256项131072B，collector核序列/身份/fault及末拍静默。四 Scala 已独立审计，联合155源8覆盖完整编译 native0：118.871542250s、观测RSS1574649856B、862class17967658B，strict cleanup/EOF完整。源码见 [MoE观察候选](../candidates/moe_router_score_observation_20261030/README.zh.md)。
- 独立官方参考候选只在原 PyTorch forward return 观察实际 router_probs 对象，不修改 forward/topk/返回/算术。baseline输出与cache逐字节检查先于保存。7项 observer 轻测通过，并非真实 Torch fixture或完整参考捕获；P7/stride8与torch.softmax差异仅报告，不创设容差、不擅认小ID tie契约。消费者 raw-score compare 与 P0 consumer 合并尚未完成，不得只复制候选覆盖现有路径。
- FAIL/INCOMPLETE 边界：联合IR已启动，但环境重连后原session84990不可读取，无终结RESULT、LOW及finalized日志。保留partial HIGH和采样，1248输入pins（含862classes）完整；当前exec隔离PIDnamespace和可取得锁不能证明原Java已消失，禁止推断native失败、通过或停止。当前新增225bits/7ports、合计119口均仅源码预期，不继承原P0实测112口。原IR重资格未重启，需原owner/session终结身份确认。
- ONGOING：GitHub唯一R3 run41096005966（source7bb6641、launchfd947e0）仍按原身份观测；source CI41095793997及launch guard41096005880成功。它使用冻结旧观察接口，独立于本候选，不把local重连当CI停止，不重复build/CI。注册五块、四Qwen3.5 eligible、P0原宿主策略延期均保持。
- 复建资格：新候选按7份已发布base/result SHA在fresh目录重建成功，16项轻量测试通过；不含完整runtime、IR/class/tensor/权重/原始日志。未改active source pins，未启动新activation。
- 完整M128 Chisel五块与最终RTL数值仍各0/5，有效MAC利用率未实测，固定4096与80%/90%目标不变。临时目录本轮407项、磁盘约20GiB可用；保留partial/唯一证据及所有输入，未删除数据。


## 2026-10-30 17时：真实观察通路发射 IR，Python DSO 准入修复（TEMP / INCOMPLETE）

- DONE（精确范围）：P0 resident gate/up 真实 SRAM 只读观察候选已完成本地原155源/5覆盖完整 Scala 字节码编译，native0，120.928s，观测RSS1589428224B，861 class。原 DiagnoseOriginalHostMoePhaseV5 随后实际发射 HIGH 与 official LOW FIRRTL，native0，151.343s，观测RSS4318490624B，严格 cleanup/EOF。该候选仍未替换 active backend。
- 本次 LOW 独立解析确认112端口：原85个端口无删除/方向/位宽改变，新增27个输出共689bits。HIGH SHA256 0beb67704eca597275afea1aa688601996aca4ffb5dfc5e2fc728b17d6179afc，LOW f52a49582417a849ea3c0d63082c5e9bbdb117aec6d79993eacc783c917ddde3。只是实际IR/接口证据，尚非生成SV、Verilator ABI、数值或PPA通过；本地DebianJava也不迁移CI Adoptium资格。
- 结构勘误：原helper已有一个UnifiedVectorElement32BankV4及其32个HeteroFP32Alu后代断言，本次LOW也独立确认该bank的32个ALU。全可达图是81个该类ALU，不是全设计仅32个。P0 SiLU16-lane/GDN scalar调度不否定已有32-unit结构，也不能把结构当成统一32-lane持续II=1。8个Matrix endpoint是接口/层级证据，不单凭端点数证明内部4096 MAC实现。
- FAIL：唯一canonical R2 run41086843436（source8cae，launch2afa）在6项准备native0后，fresh-host以PYTHON_EXTENSION / ELF_DEPENDENCY_UNRESOLVED / EMPTY_DEPENDENCY_LIST退出1，cleanup/EOF完整。未进入backend编译、runtime/reference/DUT。guard41086843454成功。保留受控摘要，不上传原始路径/库存。
- ONGOING：修复已加载Python扩展被ldd报告statically linked时的零DT_NEEDED分类。只接纳已pin、已由当前解释器加载、ET_DYN、无INTERP、完整dynamic表且无NEEDED/FILTER/AUXILIARY/AUDIT/DEPAUDIT的DSO；其他空依赖仍拒绝。本地Python3.13实物复现与synthetic测试不能证明本轮CI Python3.12具体模块，后者仍UNKNOWN。根目录许可、P0原策略、算术、硬件与资源cap不放宽。新R3源码nonce与旧4份launch隔离，source先CI，activation另提交，绝不重跑旧run。
- PASS精确范围：本次合并139项轻量metadata/lifecycle/mock/合成解析测试在normal与-O分别全部通过，非目标host或DUT验证。
- TODO：接通未覆盖的完整数值观察与比较；新观察接口须建立新的canonical/SV/ABI资格，旧hash不继承。P0原宿主策略仍延期；P1–P4只进入显式四块诊断路径，不能冒充五块通过。五块M128 Chisel与最终RTL完整数值均0/5，利用率未实测，80%/90%目标未达成证据。
- 临时数据盘点：本次IR manifest为13项439001203B，目录实际14项752045501B，额外LOW副本同hash；保留未删。17:02云端可用磁盘约20GiB、MemAvailable约8.6GiB，无本地重型作业；不启动超内存完整C++ frontend，不提交生成IR/class/权重/NPZ。


## 最新源码批：分离 P0 阻塞与四块推进（TEMP，尚未激活）

- 基于 e5801897，复用现有 entry/flow/runtime/owner/numeric 接线。默认全五合同不变；新增显式注册五块、eligible P1–P4、P0 原宿主策略延期模式。选择四块不是 CPU 缺 AVX512 的观测，也不是实际执行/PASS；不伪造 P0 receipt，owner 拒绝 P0 lease。仅两个 Qwen3.5 runtime 与四份 reference/numeric 调度，原三安装/五块时间和资源预约上界保留。
- 新鲜宿主合同只允许在原 owning bootstrap 内完成具体工具/依赖核验后进入原 build。原 JDK exact vendor/version、GNU13/14、固定 Verilator/JAR/source/canonical/SV/ABI 保持；新增固定范围 ELF/Python/shell 身份、GNU 缺库拒绝、查询专用 JDK 路径及 stage 前后 alias 核验。不是镜像白名单或整个 OS 资格，不继承旧 PASS。默认无 flag 仍执行原镜像合同。
- one_job 的监督后 alias 核验是新代码，已同步三份 producer proof 及 consumer pin 链与 manifest，并从 UNCHANGED 列表移出，单独记录 reviewed delta。旧被拒 watchdog 未纳入，原监督实现/资源 caps 不改。四个固定 fresh-host receipt 路径只导出状态/枚举/hash/计数；缺失及无效明确未资格，不上传依赖路径、环境或原始日志。
- 资源标签勘误：vector_lanes=32 是既有 artifact 声明值，不能证明真实32-lane每周期issue。已核 P0 SiLU 16-lane 源路径，GDN另有32项bank以scalar游标处理；不据此推断整个设计仅16 lanes。summary 增加 DECLARED_ARTIFACT_TAG_NOT_VERIFIED_PHYSICAL_ISSUE_LANES 和 vector_ii1_verified=false。4096 MAC约束、全部硬件/算术/路由源码未因本执行器批改变。
- PASS精确范围：合并后94项轻量 metadata/lifecycle/mock 测试在 normal 与 -O 各通过；初次合并的旧global-CPU字符串断言失败已保留工具记录，并改为检验真实profile-specific CPU合同后重测。无真实fresh-host inventory/安装/build/DUT、无新activation、无数值或利用率资格。
- 下一步：独立审查显式四块/fresh-host启动配置和实际runner准入，不能重跑已消耗activation。另有真实P0 resident gate/up只读观察候选：当前本地155源仅五文件override的Scala typer已native0（55.46s，观测RSS892080128B、cleanup/EOF完整），但本地DebianJava21.0.12不同CI，未做插件后置阶段/elaboration/RTL；该硬件/ABI候选尚未接入本批当前backend，旧哈希不得迁移。
- 完整五块128-token Chisel/最终RTL数值仍各0/5；原35B安装原因UNKNOWN。临时目录已盘点，未删运行输入或唯一证据。


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


## 2026-10-30 同 job 五块 M128 接线（TEMP / INCOMPLETE，尚未激活）

- 新增唯一未激活 workflow 与 source/launch 分离身份校验；没有启动 manifest，本提交不启动重 CI。原被拒 watchdog 新版不包含，仍用已发布监督脚本。
- 真正接线顺序为同一 4096 MAC / Vector32 backend 构建 → 原 53 archives / 完整 70 tensors 单份 → 原三安装及 fresh owner → 五块 M128 独立参考 → 原 provider → 同一 ELF 五 profile 短 wall 标定。所有数据留 job，仅允许受控 ≤64KiB 摘要上传。
- 350min 首步骤时钟；19500s 有限停止预算，另留1500s。五个300s诊断窗口不缩M128/max_cycles，不能冒完整数值PASS。旧本地5/5 Python参考与历史build资格不迁移为新 job 通过。
- 前置需实际 AVX512/Python3.12/原image和JDK、MemAvailable13GiB、free20,671,240,864B；不满足明确NO GO，不改硬件或资源门。标准runner标称存储不保证此门通过。
- Source-only 审查及轻量元数据/mock测试通过；无真实新安装、参考、DUT执行。完整Chisel数值与最终冻结RTL仍0/5，利用率没有新实测。属于Chisel测试发射IR/SV仿真backend，不是最终RTL回放。
- 下一步仅在独立复核实际资源/唯一 activation 后开展受限标定；失败沿原身份诊断，不自动重复构建。MoE同分小ID契约仍待明确。



## 2026-10-30 原同 job run 41034072605：FAIL / 具体资源原因 UNKNOWN

- source0235a207、launch1ed8612f，attempt1，原任务已终止且未重试。27个backend准备/编译/归档/link阶段native0，阶段耗时和2516.52s；实际共同ELF139,950,896B，SHA ce0bcb621646cb9286c4273d9cb819e42f1513a4b3084d0b7c76bd44ba83837c。仅hash可验证，未上传/保留可下载binary。
- SV raw c8e6b1c8…、受限SourceInfo规范化6555ede3…通过，仅仿真backend身份资格，不是完整数值或最终RTL通过。Host观察RSS9,597,370,368B，旧采样监控不是连续峰值证明。
- archive、70tensor、Qwen2与08B安装native0；35B安装阶段27.43s，native=null/errors2，cleanup与日志EOF完整。原supervisor具体错误及tree/cap数据未被摘要导出，完整公开job日志也没有，故原因保持UNKNOWN，不能因两条error猜定磁盘超限。
- 本次owner/五参考/provider/DUT均未开始，完整数值仍0/5。实际安全摘要12,031B SHA77a70f8bf677342910de92c8995f2144f0da223aa252621f5b689ccc1fa4882e，原artifact12969717356只含摘要。
- 本提交仅补摘要typed reasons/原错误hash和长度/现有资源指标，并修64KiB降级时保留真实嵌套telemetry；6小fixture normal/-O通过。没有修改监督脚本、cap、硬件、数值算法、workflow或activation；不能追补已丢失的原reason。
- 下一步先收束保活磁盘证据和原路径引用，原2.462GB inventory仅obj，不代表总job；不得先据推测提高cap或盲目重跑。


## 2026-10-30 精确两复制物生命周期接线（TEMP / 未实际去重）

- 基于57ec657d新增固定SV/ELF两对复制物去重helper及20小fixture，接在原build完全终态后、材料前。只保留两端路径的同设备硬链接去重，不清理obj目录；原四P0 producer、4096 MAC/Vector32、数值算法、cap、已发布supervisor、workflow/activation均未改。
- 准入要求27原native完整cleanup/EOF、七文件和源身份/五archive-link receipt一致、两端hash/size、effective uid和gid相同、mode完全相等、初始单链接、无symlink及可见writer。三锁内重核journal；普通失败可回滚，foreign inode或无法证明的残留保留等待诊断。禁止chmod/chown，任一mode不等整轮NO_OP。
- 20临时小文件fixture normal/-O通过仅是源码/生命周期测试；未操作真实CI数据、未删除唯一证据、没有启动新CI执行。收益0至362,153,111B仅逻辑inode存活量，不是物理free释放或整体12.081GB适配证明。原ELF可能755而pack700，因而可完全NO_OP。
- 原run41034072605的35B安装错误仍UNKNOWN，不能把候选去重当根因修复。原任务不重试；完整Chisel数值/最终冻结RTL仍0/5，无新利用率实测。下一次真实执行仍需独立审查准入与有限预算，仅摘要出站。

## 2026-10-30 安装前后whole-root快照（TEMP / 未实际采样）

- 在既有install_job的三安装前后/finally调用原已pin live_budget.census；同一native锁下仅使用未预占全job剩余时间，保留原native/cleanup/bind/tail预算。原watchdog、cap、数值、workflow/activation均未修改，不增加执行壳。
- 固定6个安全label，记录whole job+repo inode去重bytes/files/entries/free/symlink计数和monotonic起止/耗时；20s为协作检查，不是OS调用硬限。后置只在cleanup/EOF完整时扫描，否则明确UNAVAILABLE。native失败但cleanup完整可观测；结果不是失败瞬间，也不是连续峰值或资源PASS。
- 快照每条4KiB，summary严格枚举/数值/hash投影，缺失/超限/巨整数等标INVALID_FIELDS，不丢原stage，64KiB降级保留；不上传私路径、argv、原错误全文或数据。17小fixture normal/-O通过，仅元数据/模拟census，不是真实安装或目录采样通过。
- 原run41034072605的35B安装原因仍UNKNOWN，不能追认旧缺失reason；该源码只改善未来获准执行的可观察性。没有新安装/EDA/去重/删除/activation，完整硬件数值仍0/5。

## 2026-10-30：新一次性同 job 诊断启动源码（TEMP，尚未启动）

- done / PASS（仅启动接线）：以 7c545226 为源码基线，将既有 workflow 与 guard 的单次路径/nonce 更换为 five_m128_samejob_diagnostic_r2_20261030_once；保留单新增文件、精确 parent/source/event、attempt 1、实际 run/blob 身份与所有资源门。对应三项 source pin 同步更新，其余不变。
- done / PASS（仅轻量 fixture）：7 项测试在 normal/-O 各通过；含真实两提交 Git 身份、旧 activation 文件保留、旧 nonce/path 及错误事件/重试/资源拒绝。无 backend/runtime/DUT 执行。
- ongoing / TEMP：先发布并验证新源码提交，再独立审核只新增新 activation 路径的一次提交，source_sha 必须绑定实际新源码。当前没有新运行身份，不能宣称已启动或资源门已通过。
- 原 41034072605 安装失败原因仍 UNKNOWN；27-stage backend 构建不是数值通过。修复后的 typed 诊断、安装前后离散快照与精确副本候选只适用于未来运行，不追补旧证据，不保证资源适配。
- 五块仍完整 M128、同一 4096-MAC/Vector32 backend；未来每块 300 秒仅执行标定。独立 Python 参考 5/5；完整 Chisel/RTL 数值各 0/5，MAC 利用率未新增实测。未修改数值/路由/硬件/caps/旧监督程序，未上传权重或运行 payload，未清理文件。

- 同批补充：安全摘要新增固定去重 journal 的六类枚举状态、逻辑节约量、receipt/build hash 和两固定 role 状态；不导出路径/用户标识/异常全文。新增14项与既有安装快照17项元数据测试normal/-O通过。journal产生前失败仍可能为NOT_OBSERVED；COMPLETE仅为journal声明，不是独立实际去重、物理空间或数值验收。原35B安装原因仍UNKNOWN。

## 2026-10-30 diagnostic R2 实际 NO_GO：CPU_AVX512（无重构建）

- source04be815f、launch718a451e，run41064855934/job124093486574/attempt1，已completed/failure；启动身份与checkout通过，主步骤在13:38:23Z因CPU_AVX512前置停止。没有材料下载、backend构建、安装、参考/provider/DUT执行，未重跑原任务。launch提交检查41064856103成功。
- 原始log的runner ImageVersion为20261025.353.1，亦不等于固定20261026.354.1；实际首个失败仅CPU门，不能声称后续内存/磁盘/源码门已通过。
- 唯一artifact12980938760为638B摘要ZIP，SHA72191129a1b4f94c586ba8fea4c915edd64e3d9151a09225af7cb55ce387279e；解包原摘要SHA77c91397c306fba7c583ffe821ea1def2c7e50de3c322ce5d0e0d790a4afdacd，stages空、numeric_pass=false、dedup NOT_OBSERVED。未上传payload。
- 下一步审核宿主CPU/工具版本绑定的真实依赖，不能直接删除AVX512或镜像门、盲目重试或迁移旧参考PASS。原35B安装原因仍UNKNOWN；五块完整Chisel/最终RTL仍各0/5，有效MAC无新增实测。

## 2026-10-30 P0 宿主 dispatch 实测（FAIL_BYTE_DIFFERENCE，非硬件）

- 未重试CI。当前本地AVX512宿主上，复用原runtime/官方forward/权重/刺激/FP32-BF16规则，A=AVX512四线程、B=default四线程、C=AVX2四线程。A/B串行，C独立新目录复用已核A；原V2 lease及监督资源cap不变。三捕获native0、cleanup/EOF完整，两个严格比较入口均exit1。
- 独立复核全部24项导出张量文件：A与原参考24/24逐字节一致；B与C均23/24。唯一差异为注意力概率stage.self_attn.0.1的196608个BF16元素中1个编码相差1，最大绝对差5.820766091346741e-11。最终输出和KV完全一致仍不升级严格中间张量等价；两试验均FAIL_BYTE_DIFFERENCE，不替换原参考、不修改阈值。
- PASS只限捕获进程完成、身份/文件哈希核验和相应相同张量；没有Chisel/RTL/DUT执行。ATEN AVX2不保证底层MKL/oneDNN不使用AVX512，本地试验不认证实际非AVX512宿主。只检查24个导出张量，不声称官方函数内部全部中间值已观测。
- 发布仅安全摘要、receipt/recipe哈希与策略差异；本地binding、运行库、权重和张量数据不出站。两套轻测分别7/8项normal及-O通过。源码/FAIL/原数据均保留，没有清理。
- 重执行仍缺符合原P0及具体工具身份的足额AVX512宿主；不能在随机standard runner上反复碰运气或直接删除CPU/image门。原35B安装错误UNKNOWN不受本实验解释。完整五块M128 Chisel/最终RTL仍各0/5，无新增MAC利用率实测。

## 2026-10-30：Qwen3.5 四块 fresh-host 一次性启动接线（TEMP，未 activation）

- done / PASS（仅源码/轻测）：以已发布 4e2407d5ee830de261511c1f6ad0e8a5b0075b05 为基线，新一次性路径和 nonce 为 qwen35_four_m128_freshhost_20261030_once；schema/profile 明确 registered5、eligible4、P0 deferred、fresh-host。既有 prepare_and_run 入口显式传入 QWEN35_FOUR_P0_BLOCKED_ORIGINAL_HOST_POLICY 及 --fresh-host-profile；仅三项 source pin 更新，其余不变。
- done / PASS（仅 fixture）：9 项 normal/-O 测试分别通过，覆盖新路径/nonce、两份已消耗 activation 保留及拒绝、旧全五块 schema/profile 拒绝、flags/scope 绑定、实际 Git 身份、重试/额外文件/错误资源和事件拒绝。未运行 target host 资格、backend、runtime 或 DUT。
- ongoing / TEMP：先发布上述源码并核验 CI，再单独审核仅新增新 activation 文件的提交，以实际新源码 SHA 为唯一 parent/source。当前未创建 activation，不能称四块已启动。新 host 必须通过既有有界 prebuild 契约，尚未 qualified。
- 保持五 profile 登记：P1–P4 是本次执行候选；P0 按原 host policy deferred / NOT_TESTED，不改其数值基线，不计入已通过。共享完整 4096-MAC 硬件定义未改；vector_lanes32 仅声明 tag，不代表物理 32-lane II=1 已验证。
- 原资源上限、21000秒总时限、并发互斥、每块标定时限和仅上传受限摘要保持。所有历史 activation/失败材料保留，不重跑旧 run、不清理、不上传权重/二进制/原始参考。完整五块 Chisel/RTL 数值仍需真实完成；本次接线测试不能替代数值或 MAC 利用率实测。

## 2026-10-30 四块新宿主运行终态与真实 SRAM 观察候选

- 运行 41081287332（job 124150795368，attempt 1；source 0ebe665a，launch edaf391f）的主步骤已失败。JDK、GNU tool inventory、JAR、Verilator、iDMA、Matrix 六个准备阶段均 native 0；fresh-host inventory 为 native 1，原因码 ELF_DEPENDENCY_ROOT_REJECTED，cleanup/EOF 完整。未进入长 backend 编译、runtime 安装、reference 或 DUT。P0 是策略延期、未测试，不能称实测 CPU 缺 AVX512。
- 原安全摘要为 19,228 B，SHA256 c330617708d91025fcdc91eacd037b9510f2442fec28730d0a6880f3c1b991d1；artifact 12989501775 的 ZIP SHA256 为 9f9e7abe53f806ee272e7b9adba60e5100064b11004d1ed4d16a3bdac6996a9d。拒绝路径未导出，不能猜定原现场路径。只读本地 JDK ldd 显示合法 bin/../lib 路径会被现词法门误拒绝。这是已复现的本地代码缺陷，不等于原 CI 具体根因已完整定位；不重试旧任务。
- 本批发布 candidates/p0_resident_observation_20261030 隔离源码包：从真实 sealed SRAM gate/up 读响应输出 valid-only 观察口，统一 689 bit / 预计 27 port，配套最终 V3 driver collector 和实际 consumer_owned 位比较器。无 ready 反馈，不改算术或 DDR。参考 BF16 位扩展后与 actual 原始 FP32 精确比较，不舍入 actual。该包未替换 active fixed155/backend，原规范化、ABI、RTL 哈希门禁保留。
- 实际本地 Scala typer：155 份源码、五文件 override；native 0，用时 55.460118529998 秒，观测 RSS 892080128 B，严格 cleanup/EOF/gzip 完整。receipt SHA256 为 81f6b9f1bf1f8243c874d45a9a2d6054e4ca7828f103cb9243960b5f4af3d4ba。Debian Java 21.0.12.1 不同于 CI Adoptium 21.0.13；-Ystop-after:typer 不覆盖插件后置阶段、字节码编译、elaboration、真实 ABI、RTL 或数值。C++ 完整 shape 合成 collector、mock-port 语法及 Python helper/owned 测试只按各自范围通过。
- 后续需将观察包与新 source overlay、driver/header、owned-helper pin 链、新 ABI 及实际规范化/RTL 身份共同资格化，不能迁移旧 85 port 或旧 canonical PASS。MoE raw scores 观测及其余 required stage 比较仍未补齐。整个设计的物理 Vector32/II=1 未证明。五块完整 Chisel/RTL 各 0/5，无新增利用率实测；原 35B 安装原因仍 UNKNOWN。

## 2026-10-30：修复合法 ELF 相对路径拼写的误拒（TEMP，未激活）

- 原运行 41081287332 的确切拒绝路径仍未导出。对本机可信 Java 的只读 ldd 和两版解析器直接调用，复现了 bin/../lib/libjli.so 被旧词法规则误拒绝；这只证明本地缺陷，不回填原 CI 未观测路径。
- 新解析先核规范化词法入口，再 strict resolve 并核实际普通文件仍在原系统/toolcache 根族内。合法内部 .. 可通过；真实越界、symlink 逃逸、缺失和目录仍拒绝。保留 raw→canonical alias、实际文件 hash、pin 时重核及原 stage 前后核验。没有扩大根族或资源/版本/硬件/数值合同。
- 失败投影增加固定 query_role、rejection_kind 和 bool had_parent_component，拒绝任意字符串/路径及错误类型；旧 receipt 不凭空补 query_role。公开只给受限标量/hash，无原始 ldd、机器路径或库存。
- 新 unique canonical R2 path/nonce 仅是源码接线；schema/profile、eligible P1–P4、P0 原策略延期、两 flags、预算/并发/摘要限制不变。全部已消耗 launch 保留并拒绝重用。source 与之后的单文件 activation 必须分开。
- PASS 范围：119 项合并 metadata/lifecycle/mock/launch 测试在 normal 和 -O 各通过；本机可信路径解析复现通过。没有新 host inventory、backend、runtime、DUT 或数值通过。下一步必须绑定本源码新身份后做一次独立受限运行；不重试旧 run。

