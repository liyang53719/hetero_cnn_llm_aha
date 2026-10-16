# 后续最小连接计划（尚未实现）

## 已验证完整 M128 合成 Attention（2026-10-16）

CI38885333680/job116921584236于10:28:09完成，回执PASS_M128_SYNTHETIC_ATTENTION。原始PV16 owner的direct及共享A贷款路径均执行真实m=128作业，独立参考逐项中间检查与完整scalar/Matrix/core/write散列全部一致；71项输入和库/回执前后不变。安全摘要见m128_evidence.json，原artifact12040601089的SHA256为fbcbededfd0cdab1c06d8fe01a145ba0afa211aabb621abfe5e5ab4ca1543102。

总墙钟1109.012743秒：direct303.965708秒，loan802.100178秒，参考2.407196秒；峰值RSS62328KiB。每pass保留55480320个标量操作、1585152个legacy Matrix请求及811597824个native FMA。KV的1585152次核心读取对应4096次DDR miss，Q的12288次读取不变；12288个输出写ACK覆盖196608词，最后line4095已检查。

这些是合成数据的完整Attention主机数值结果。尚未完成Qwen2完整block128、原始projection/MLP策略故障修复、消费端RTL或硬件性能验收。贷款减少KV外存请求，但不减少原Matrix/标量工作；墙钟更慢，不能把软件工作计数或有用/执行FMA比称为硬件利用率。原native_policy_acceptance仍为UNCHANGED_FAIL_POLICY_PENDING。

- 已完成：原始Attention M128数值及传输链验证、安全证据核查。
- 进行中：核查既有Qwen2完整block入口与projection/MLP数值故障，准备最小模型连接和短测。
- 待完成：完整block128经审查的实际运行；consumer/parent RTL与性能/资源证据。

## 历史准备记录（保留当时状态；当前结果以上文为准）


1. 原始 chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala：仅在 attLocal 的 K read 和 attProbScale 的 V read 分流；保留 packet、attDot、attPVCompute 和所有算术。新增默认关闭接口及显式故障消费抑制，不能把模型侧带当成已有功能。
2. 同目录 QwenOwnerProtocol.scala：在现有 mode-0 memory 仲裁中连接元数据缓存/贷款状态机。先接受核心读，再获得原 Down owner 贷款，再发 DDR miss；匹配 DDR reply 与 raw fill 同步接受。错误路径不修改原债务身份。缓存位仅在 clean fill ACK 后置位；用 raw reread 供数，不加数据影子。
3. 同目录 HostBlockTop.scala：只传播默认关闭参数/既有父模块连接。保持原顶层与核选择；mode0/active 在核心 held completion 和所有请求/ACK/lease 退休前不能切换。不得用全局 Matrix idle 阻塞 Attention 的借用。
4. 上述 patch 必须在当前完整原始 patch 组合后单独应用、单独固定哈希；保留已验证 raw bank 基线。先完成父模块 RTL 生命周期证据，再审查最小消费者 unit。禁止通过强制内部寄存器模拟 retained-A 生命周期。

## 失败状态表

- idle→acquire：接受一个合法核心读，建立 core_pending；若已故障，转 error_response。
- acquire→lookup：实际父模块 grant，retained-A 必须先一拍失效。故障转 error_response，无 DDR 债务。
- lookup：命中转 read_issue；未命中转 miss_req。
- miss_req→miss_wait：仅 DDR 请求接受时建立 ddr_pending；已 offered 请求即使 abort 也保持 valid/身份到 ready，然后排空真实返回。任何无债务的 supplier 回复均毒化。
- miss_wait：外来回复毒化但保留原债务；匹配错误/撤销回复退休 DDR 并转 error_response；匹配成功回复只有 raw fill 接受时才退休 DDR。
- fill_wait：稳定 raw 回复至 matching ACK；clean ACK 提交 valid 后转 read_issue；故障 ACK 排空后转 error_response。
- read_issue/read_wait：raw 同步读及稳定 held reply；核心 valid/ready 消费后撤回回复；若 raw ACK 尚未 ready，转 ack_wait 保留 raw 债务，后续 matching ACK 才退休。故障侧带禁止使用数据。
- error_response：稳定原 tag 错误直至核心消费。
- terminal：关闭新读；保留 mode0/active，等所有债务退休后释放贷款，再允许原 host completion。该门控不依赖 completion.ready。

## 验收界限

首批六文件是模型/来源/短测计划，不包含 consumer RTL。后续 M1/M2 原始算术数值结果见下文；M128真实执行、端到端吞吐、DDR性能及硬件资源结论仍待后续单独测试。父模块已编译/展开的结果不能代替其尚未完成的 RTL 生命周期验证。

## 原始数值消费者的小规模桥接（M1/M2已执行，历史设计）

新增 numeric_bridge.py 测试适配器，不改 OfficialAttentionOwner 的 tick、_attention、_matrix_step、ScalarService 或 MatrixService。只把原 owner 已接受的 K/V MemoryRequest 接到 KvSupply；Q读与输出写仍走原测试 Bus。接受与返回的身份、64B容器顺序保持不变。供应侧故障通过现有 Python local_reset 进入 owner 的 drain，再消费 held reply；这验证 Python 排空契约，不代表 Chisel 已有该故障侧带。

两组短数值比较只用合成 M1/M2：原 DDR 路径与贷款路径分别运行原始 owner，比较输出逐位值、完整 scalar 操作序列、QK dot/score、接受的 Matrix 请求/FMA计数（不比较因传输停顿而改变的 legacy_model_ticks），并复用原 independent reference_attention。加入背压、故障排空和最后 raw ACK/贷款释放前的终端门控。有效数值测试使用有限输入；NaN/Inf原位传输仍由现有26项纯传输测试覆盖。

numeric_prepare.py 和 test_numeric_prepare.py 是普通发现测试，只验证52项已固定依赖及来源，不导入/执行原算术服务。numeric_pins.json 固定当前033ac109来源。数值入口必须显式选择，要求 MATRIX_SERVICE_LIBRARY 及相邻 compile.json，复用原 verified_library 的来源、编译参数、库散列校验。无库时返回 NOT_RUN 且退出码非零，不能用 skip、stub或临时编译获得 PASS。

当前隔离目录没有该库，也没有真正的 git checkout；原 ScalarService 的 source_identity 要求 git HEAD 中 recipe 原文匹配。后续可在已有标准 Matrix CI 的真实 checkout 与已验证库上下文中单独扩展短测，先审查再运行，不绕过源检查。此批不创建新工作流、不启动编译、不上传合成数据或完整算术轨迹。只允许输出状态和计数摘要；不能据此宣称 M128、公有模型数值验收或硬件时序通过。

## 既有 Matrix CI 的最小数值扩展（M1/M2已执行，历史设计）

仅在 .github/workflows/qwen2-matrix-interface-frontend.yml 原有 job 中，普通 contracts 测试之后、长 Scala 检查之前，加一次 run_attempt==1 的 run_numeric_ci 调用。继续复用既有 build_shared_matrix_recipe 产生并通过 GITHUB_ENV 导出的库/回执；wrapper 只调用 from_environment 校验，不调用 build。保持原触发路径、一个 job、20分钟总时限及既有编译步骤。最近已观察到约17分钟的总运行，因此新增 wrapper 的120秒总预算包含最多5秒清理（子进程至多114秒并扣除准备时间，另留1秒回执写入），不延长 job 时限；实际余量仍须以本次日志确认。

新增52输入检查包含严格共享库构建验证器、原始 native 编译闭包及已测试的进程组清理 helper。运行前后冻结原始依赖、adapter/runner、owning workflow、library 和 compile receipt 的散列；发生漂移不能 PASS。复用 start_new_session 及 SIGTERM/TERM/KILL 的全组清理，不重试、不增加 native 编译。

只有 work/raw-kv-attention-numeric/summary.json 与 source_hashes.json 加入原有 artifact 的显式清单。子进程原始输出保留在临时目录，绝不添加到既有递归上传路径或打印到日志。成功必须同时有 M1、M2 及故障排空的固定摘要，缺库、超时、异常、非零返回或摘要不匹配均不是 PASS。输出仅为固定状态/计数与来源散列，不上传数据、权重、完整标量轨迹或绝对本地路径。


## M128 独立阶段：源码工作量与当前状态

原小规模桥接 CI38876783404/job116893624170 在472bd304完成 SUCCESS；PASS_BOUNDED_NUMERIC wall1.157524秒，M1/M2及故障案例已验证。旧回执保留，原 runner 默认行为不改写。

完整 M128 Attention 的原调度每次执行有8256个因果 token/key组合、99072个 head/key组合、1585152个 KV读/legacy Matrix请求、12288个 Q读、12288个输出写、4096个唯一 KV行及196608个输出词。原 profile0 每请求512个 native FMA，总811597824个；每请求返回完整16KiB矩阵快照，约24.2GiB累计临时返回字节。原 lazy MatrixValue 已避免4096个 Python整型逐次展开，必须继续保留全部原返回/债务事件，不能换成 profile1 或 final-only。

受控输入下标量调用55480320次；原 RecordingScalar 全量tuple历史和原200000事件上限不适合 M128。只改变测试观测存储：流式记录操作、操作数、结果、策略及顺序的完整散列，保留有界参考中间量与逐项比较；不得改变原 owner/Scalar/Matrix 的算术节点。以上都是软件工作计数，不是硬件周期。

独立参考仅接受证明范围内的合成 BF16输入，保留 QK16stripe累积及顺序fold、原softmax每节点FP32舍入、PV按key累加和BF16输出。vectorize仅沿独立head/key/column，禁止用np.sum/dot/exp替换原顺序。每次FMA必须验证乘积/累加器的共同二进制网格和≤53有效位界限，才能用float64精确乘加后一次FP32舍入；不宣称任意FP32输入都满足。M1/M2/M4与原Fraction参考逐位交叉验证后再接受该参考。

M4/M8原生开销标定为独立小阶段，复用已有验证库，不增加编译；先审查后运行。根据实际标量、Matrix、传输和参考耗时选择 M128 独立预算，不把120秒小规模 runner 或20分钟既有整体CI直接加大。M128尚未执行，消费者RTL也尚未开始。

首批代码已准备：streaming.py/test_streaming.py（7项冷测）、reference_profile.py/test_reference_profile.py（6项小规模独立参考测）、profile_numeric.py/test_profile_numeric.py（5项来源/调度测）。合计18项普通/-O通过。引用原 ScalarService/MatrixService 后只增加观察回调，完整运算和完整16KiB返回仍执行；native direct/loan 串行运行，绝不同时占用一个累加器。旧 M1/M2入口和历史回执不改写。

M4/M8候选将逐项检查原标量运算/策略调度、原始及BF16点积、score、exp权重、每个softmax前缀和、inverse、原始及BF16概率、原始PV和最终输出；同时比较所有scalar操作数/结果、所有完整Matrix返回、全部核心请求及输出写的有序散列。精确检查Matrix包/组/结果/完成/owner释放数量、KV miss/hit/fill/release、Q读和输出ACK。终端还保持三拍检查稳定性。报告各pass软件事件/墙钟、峰值进程RSS、参考字节和来源散列，不报告硬件周期。

已准备在既有 Matrix workflow 的同一步中扩展 M4/M8：先建立单一120秒绝对deadline，完成冷测及原M1/M2后，仅把剩余时间交给标定wrapper。保留5秒进程组清理和1秒回执预算，不增加job/触发范围/20分钟总上限。新执行源冻结64项，外部wrapper再固定自身及测试共66项；新增artifact仅标定summary.json/source_hashes.json。缺少剩余预算返回非成功NOT_RUN。该扩展后续已执行，结果见下文。M128最终预算须以真实M4/M8标定结果选定，不能按简单线性估算宣称已经可运行或通过。

标定wrapper准备验证：8项新增冷测及原15项wrapper测均通过，包含真实短睡眠进程组TERM/KILL清理、过期deadline拒绝、严格计数/类型/散列/字节上限、无额外编译与双JSON白名单。与现有传输/数值准备/流式参考检查合计75项普通/-O通过（各约5秒）；另4项workflow精确范围guard普通/-O通过，保留原898e1ced基线散列。这些不是原生M4/M8执行结果。

## M4/M8 已执行与单次 M128 准备（2026-10-16）

Matrix CI38882236993/job116911473010 的09:45回执为 PASS_CALIBRATION_ONLY，墙钟8.587483秒，峰值RSS43440KiB。M4 direct/loan为0.520282/1.303913秒，每pass73152个scalar、1920个Matrix请求、983040个nativeFMA；M8为1.796507/4.518473秒，每pass253440个scalar、6912个Matrix请求、3538944个nativeFMA。独立参考分别0.0197/0.0333秒。全部流式散列/逐项中间检查逐位匹配。M8核心KV6912次，DDR256次，Q768次保持原路径。

该标定输入manifest为100e9ba7dc4d3d24323166426c78cd798b3e92c2e81ec6ee9857a2b8c563c121；库散列46b4d7b5987fad2a241c4894e61e15360c40336edb78e037eea314b63da448b1。原M1/M2、M4/M8入口及历史回执保留。

- 已完成：M4/M8真实原生开销标定和完整中间/流式结果检查。
- 进行中：独立单次M128入口、71项来源冻结、超时排空、安全进度与专用workflow审查。
- 待完成：审查通过后执行真实M128合成Attention，核验结果；消费端RTL和完整block仍未执行。

M8 direct+loan6.31498秒按因果pair比229.333估算约1448秒，只用于预算选择，不是性能保证。独立runner总上限2400秒（包含5秒进程组清理和1秒回执），专用job45分钟；一次尝试，无自动重试。只构建一次既有验证库，不引入Scala/RTL。workflow仅自身文件在main改动时触发，也可手动触发，run_attempt必须为1。

m128_numeric显式入口只执行一个m=128作业的direct pass，再串行执行一个loan pass。复用原PV16 owner、全部profile0请求/结果、原native算术及独立网格证明参考，不更换矩阵模式。每pass核验196608输出词、12288写ACK、4096唯一KV行及最后line4095；比较所有原有中间节点和完整有序流散列。完整M128仍未运行。

进度文件每约5秒及阶段转换时原子覆盖，仅固定阶段枚举、序号、墙钟和软件事件/标量/Matrix计数，≤1024字节；不会提前写PASS。结束或超时后wrapper再次验证并净化进度。artifact仅summary.json、source_hashes.json、progress.json；不上传数据、原始输出、权重或完整轨迹。超时/缺库/漂移/计数或数值错误均非成功，部分进度不能代替最终验收。

M128准备验收：新增5项入口/进度/workflow范围测试与11项wrapper测试通过；包含旧入口在内合计91项普通/-O均通过（各约5.4秒）。独立wrapper审查34项普通/-O通过，独立入口/原调度审查通过。以上均为冷测，未调用原生M128执行；发布新workflow会触发一次真实运行，须由发布方在审查后决定。
