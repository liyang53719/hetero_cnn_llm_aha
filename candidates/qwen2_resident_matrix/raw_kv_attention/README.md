# 原始 mode-0 Attention 的共享 A KV 供数模型

## 已验证完整 M128 合成 Attention（2026-10-16）

CI38885333680/job116921584236于10:28:09完成，回执PASS_M128_SYNTHETIC_ATTENTION。原始PV16 owner的direct及共享A贷款路径均执行真实m=128作业，独立参考逐项中间检查与完整scalar/Matrix/core/write散列全部一致；71项输入和库/回执前后不变。安全摘要见m128_evidence.json，原artifact12040601089的SHA256为fbcbededfd0cdab1c06d8fe01a145ba0afa211aabb621abfe5e5ab4ca1543102。

总墙钟1109.012743秒：direct303.965708秒，loan802.100178秒，参考2.407196秒；峰值RSS62328KiB。每pass保留55480320个标量操作、1585152个legacy Matrix请求及811597824个native FMA。KV的1585152次核心读取对应4096次DDR miss，Q的12288次读取不变；12288个输出写ACK覆盖196608词，最后line4095已检查。

这些是合成数据的完整Attention主机数值结果。尚未完成Qwen2完整block128、原始projection/MLP策略故障修复、消费端RTL或硬件性能验收。贷款减少KV外存请求，但不减少原Matrix/标量工作；墙钟更慢，不能把软件工作计数或有用/执行FMA比称为硬件利用率。原native_policy_acceptance仍为UNCHANGED_FAIL_POLICY_PENDING。

- 已完成：原始Attention M128数值及传输链验证、安全证据核查。
- 进行中：核查既有Qwen2完整block入口与projection/MLP数值故障，准备最小模型连接和短测。
- 待完成：完整block128经审查的实际运行；consumer/parent RTL与性能/资源证据。

## 历史准备记录（保留当时状态；当前结果以上文为准）


默认关闭。当前实现为软件传输/数值桥接模型，不修改 Chisel。

## 已验证的小规模数值结果（2026-10-16）

Matrix CI 38876783404，job116893624170，commit472bd304，已完成 SUCCESS。08:56:50 的 wrapper 回执为 PASS_BOUNDED_NUMERIC，墙钟1.157524秒：

- M1：192个 KV请求，32个 DDR miss，160个命中，1536个输出词，8244个标量操作。
- M2：576个 KV请求，64个 DDR miss，512个命中，3072个输出词，23184个标量操作。
- 故障案例 PASS：撤销 held 回复后新增算术操作0，输出未发布。

这是原 OfficialAttentionOwner、原 native Matrix/Scalar 和独立参考的小规模合成数值验证，不是 M128、完整 block、消费端 RTL 或硬件吞吐结果。原始 M1/M2 runner 默认行为、阈值与历史回执保持不变。

## M128 下一步

- 已完成：核查原 PV16 owner 支持 M128，原始调度工作量见 IMPLEMENTATION_PLAN.md。
- 进行中：有界流式观测/完整中间事件散列、受严格网格证明约束的独立参考，以及 M4/M8 原生开销标定准备。
- 待完成：M4/M8标定已完成，当前审查独立 M128 预算和入口；实际完整128-token Attention、M128数值验收及 consumer RTL 尚未运行。


## 计划与状态

- 已完成：绑定原始 OfficialAttentionOwner 的 PV16 地址顺序、原始 Qwen2ContinuousBlock 的 K/V 读取点及 official_bf16 两处 Attention 数值策略补丁；固定来源散列。
- 已完成：使用 ParentLoan、原始 DenseReductionOwner 及同一个 A Banks 的传输状态机；独立核心请求、DDR 请求和 raw 请求债务。
- 已完成：26项测试在普通 Python 与 -O 均通过（各约2秒），source contract 检查通过；4096 条容量映射及原始位模式填充/命中检查；M1/M2 小规模源顺序轨迹；故障、背压、ACK、释放及排他控制测试。
- 进行中：独立审查软件模型及后续接口契约。
- 待完成：真实 mode-0 消费端连接、父模块 RTL 生命周期验证、M128 执行及数值/性能验收。这里没有这些 PASS 结论。

## 边界

数值锚点为 official_bf16/owners.py 的 OfficialAttentionOwner._attention，PV 每次16个元素。不能用 ResidentPV32AttentionOwner 替代。source_contract.py 固定完整原文件及方法 AST，并零模糊应用原有两处 Attention 策略补丁后固定 Attention 区域；只投影 K/V 地址循环，不执行或改写算术。保留 QK/PV Matrix 边界、BF16 物化、softmax 标量顺序及输出物化。当前 source checker 不是全块编译器。

Binding 关联已接受的 Attention 作业、owner、K/V 地址和输出跨度。M1..128，每个 K/V token256个 FP32 元素；全部地址64B对齐且 K/V/输出不重叠。K 占 line0..2047，V 占 line2048..4095；实际可访问范围由 tokens 限制。每次绑定/释放/故障清空有效位，不复用跨作业缓存。原始核心读 tag 为64位，允许0；内部 raw serial 为非零32位，耗尽即报错，永不绕回。

有效位只有4096bit（512B）。模型保留有界身份、请求和债务元数据，没有新增 payload SRAM 或512bit填充影子。唯一数据存储为原始 A Banks，命中响应引用其已有 raw held response；DDR miss 数据只在 raw write 接受的同一拍被消费。填充 ACK 后才发布有效位，再从 raw bank 读回供核心消费。Python对象/计数器不是 RTL 寄存器面积证据。

## 故障与完成契约

首次核心 KV 请求被接受后才申请贷款；必须等原父模块债务及 retained-A 失效完成。贷款成功后才发 DDR miss，Dense/Tile 排他由实际 ParentLoan 执行。DDR 返回 ready 事件与 fill 接受严格相同。匹配 DDR error 不填充，产生一次原 tag 错误回复。已选中的 supplier 在没有 DDR 债务时收到回复也会消费并毒化；默认关闭时忽略该未选中接口。DDR miss 一旦 offered，valid/身份在 abort 下仍保持到 ready，接受后等待匹配回复排空。外来/畸形 DDR 回复被消费并毒化，但不清除原 DDR 债务；仍须等真正匹配回复才能排空。若真正回复永不返回，模型不会虚构完成。

作业绑定后、首次请求前的父模块故障允许接受一次原核心请求并返回带 tag 错误，避免等待贷款造成死锁。任何 accepted 请求均保留债务到对应退休事件。abort 不取消已接受 DDR/raw 事务。held 成功回复在故障下仍保持内容、tag、error 不变；reset_required 为额外粘滞故障信号。

重要：现有 Chisel 核心没有独立 reset_required 消费抑制接口。本模型要求的该侧带是后续新增契约，尚未实现。消费者必须在它为真时抑制算术/发布并消费 held 回复以排空；不能假定原核心已支持。外来 DDR 回复不得直接送入原 memRsp 的 mismatch 处理路径。

terminal 是核心完成已可见的通知，不依赖 host result.ready；它关闭新请求。核心响应 valid/ready 消费后即撤回，不等待 raw ACK；ack_wait 仅保留 raw 债务元数据直到 matching ACK，禁止重复供数及提前释放。done_ready/released 是模型 tick 的退休事件，只有核心请求、DDR、raw ACK 及贷款释放都结束才产生；未来 Chisel 必须用稳定 completion gate 保持 active/mode0，直到所有债务释放。没有全局 Matrix idle 条件，Attention 可继续使用 Matrix。

## 短测试

从仓库根运行：

    python -m unittest candidates.qwen2_resident_matrix.raw_kv_attention.test_model
    python -O -m unittest candidates.qwen2_resident_matrix.raw_kv_attention.test_model
    python -m candidates.qwen2_resident_matrix.raw_kv_attention.source_contract

M1/M2轨迹分别192/576个核心 KV 请求，32/64个唯一 DDR miss；计数来自接受事件，不将核心请求字节当成 DDR 节省。4096条覆盖是容量传输测试，不是 M128 Attention 执行。无硬件周期、利用率或数值准确率声明。

## 原始数值模型桥接准备

numeric_prepare.py / numeric_pins.json 固定52项原始依赖；test_numeric_prepare.py 供普通测试发现运行。numeric_bridge.py 为单独 opt-in 数值入口，使用原 OfficialAttentionOwner、ScalarService、MatrixService 和原独立参考，只替换 K/V 的供数路径。源码、构建回执和库必须全部验证；缺少 MATRIX_SERVICE_LIBRARY 时以 NOT_RUN 非零退出，不回退到新编译或模拟算术。

此隔离目录未运行数值桥接；后续 CI 已完成 M1/M2 比较与故障排空，结果见本页开头。准备测试本身不计作数值测试。详见 IMPLEMENTATION_PLAN.md 的桥接章节。

准备验证：8项 preparation 测试在普通 Python 与 -O 均通过（约0.3秒）；包含源码漂移拒绝、缺库 CLI 非成功退出及纯协议 DDR 解码检查。未调用数值入口的执行分支。

    python -m unittest candidates.qwen2_resident_matrix.raw_kv_attention.test_numeric_prepare
    python -O -m unittest candidates.qwen2_resident_matrix.raw_kv_attention.test_numeric_prepare

后续显式数值入口为 python -m candidates.qwen2_resident_matrix.raw_kv_attention.numeric_bridge；需要已有已验证库。入口设置120秒协作式墙钟检查和每次200000事件上限；已准备在既有 Matrix CI 中显式调用；未增加新工作流或触发范围。

CI扩展已执行并通过上述小规模案例：在既有 qwen2-matrix-interface-frontend job 的普通 contracts 后运行一次 opt-in wrapper；继续复用已构建库，120秒总预算含清理，保持20分钟 job 上限。只保存 summary.json/source_hashes.json，不保存原始子进程输出。数值 PASS 范围仅为上述 M1/M2 与故障案例。

CI wrapper 的15项冷测试普通/-O通过（每组约1.4秒），含真实短睡眠子进程组清理、严格摘要、输入漂移和缺库路径；与26项传输、8项准备测试合计49项普通/-O通过（每组约3.4秒）。这些测试没有载入 native 数值库。当前 wrapper 冻结58个仓库输入以及库/回执散列，114秒工作预算加5秒清理和1秒回执写入，最终绝对上限120秒。

M128准备的首批实现：streaming.py 仅观察原服务并输出完整有序 scalar/Matrix/core/write 散列，已删除未使用的大型 collector；原 Bus 的 trace/reads/writes 测试历史改为有界散列/计数，不改其请求/ACK行为。reference_profile.py 的整数网格证明和 M1/M2/M4 Fraction逐位交叉检查已通过。profile_numeric.py 只开放显式 --calibrate 的 M4/M8；M128仍仅做计数核查，不可由该入口执行。

新增18项准备测试普通/-O均通过（约0.7秒）。新文件及原依赖共64个来源项、已有库及回执在候选执行前后冻结/比较。此前准备阶段尚未运行M4/M8；现已执行，结果见下文。外部硬时限wrapper与既有CI扩展已准备并待审查：冷测、原M1/M2和M4/M8共用120秒绝对deadline；旧M1/M2回执单独保存，新增标定仅上传两份安全JSON。wrapper冻结66项源输入，并保留5秒进程组清理，不增加既有20分钟job预算。

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
