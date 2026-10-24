# 真实 selected Attention generator 的 ordered fold 接入

默认关闭；本包只推进 generator 的真实小规模数值路径。不是完整 owner/public runtime、fullblock、native 或 RTL 资格。没有改已发布 selected/direct 包、生产源码、历史 pins 或 observer。

## 实际最小改动

`selected_schedule.patch` 对已发布 `qwen2_selected_scala_model/schedule.py` 的运行后像仅加入：

- `ProductionQk16Schedule(ordered_fold=False)`，exact bool，默认执行原逐 key Scalar reduction 原代码。
- 明确开启时，真实 token/head/QK depth generator 在第8个 PackedRequest 返回后创建一个 `OrderedFoldWork(result, count, maximum)`，反复 yield 同一工作项，逐 key 接受实际推进器消费过的 retirement 对象，再 append score/update maximum。
- 仍由原 generator 在全部当前组 score 提交后 yield 原 `PackedConsumerAck(result.tag)`。Q/K/V地址、Matrix输入 BF16、QK8步、每head softmax/exp7/div、legacy PV及输出物化都不改。

`ordered_work.py` 提供单工作项推进器，不是通用SFU或第二个ScalarService。它借用原 live result，16个acc和16个sticky fault；16 stripe scan→16 ordered Add→BF(dot)/strict Mul/BF(score)→顺序退休。尾lane不读、不算。错误仅在对应key退休时向generator报告，既提交前缀不回滚。

`StrictLaneOps` 必须显式给出 Add/Mul/BF/finite 回调，没有宽松 fallback。NV/DZ/OF/UF mask=0x1e，NX单独允许；finite结果再次检查。不调用owner.scalar、不新增ScalarService、不使用忽略UF的旧vector policy。软件测试用原公开ref_add/ref_mul/ref_bf与exact Fraction辅助函数，有限运算的OF/UF/NX按精确数学值和RNE结果推导；不是模拟实际HardFloat flags导线。

工作项回复有ready/持有及单次消费协议。必须是该work实际握手的原response对象、正确key/终态和canonical类型，不能提前伪造末key或重放；前一个response未由generator消费前不能切换work。result_valid=False与abort抑制响应消费。推进器从不代发Matrix ACK或自行清理client债务。

## 本批明确没有接通的入口

本片只把工作项接入真实 `ProductionQk16Schedule.run` 并由原数值driver推进。没有改 `entry.install`、direct transport或 `AttentionOwner._advance`/packed hooks。原owner只识别PackedRequest/Ack/Scratch和memory操作，尚不识别OrderedFoldWork，故不得在其完整运行环境手工开启该开关并宣称可运行。

prepare仅输出两文件partial overlay；完整owner hooks、严格运行后端、profile2 native闭包、full suffix dispatch、只读observer和新full profile准入是后续独立片。本包不删除这些门，不改旧type/pins使其假通过。

## 对应身份

SOURCE_PINS.json 绑定已发布 selected schedule 的原始/新后像、原 numeric harness，以及目标Chisel core postimage：
`9120b040016116ae400389fe027bdb26e4b6d450faeeef6dba058108d32ba48c`。

该Chisel候选与本片保持scan/fold/scale/逐key退休算术顺序。工作项ready/response是软件generator适配协议，不是Chisel额外寄存器/时序证明；Python对象、计数和测试观察缓冲也不能作为硬件资源清单或周期。

## 真数值测试与精确范围

`test_numeric.py` 加载并校验已发布 `test_schedule_numeric.py` 的原样模块；该模块只执行固定定义AST，不导入生产native/NumPy前言。复用其 `ProductionDriver` 的真实QK packet/Fraction FMA、live FIFO视图和原legacy PV adapter。新driver仅处理额外work请求；其余请求走原driver。

M1和M2：比较开启/关闭两种真实selected generator的全部1536/3072个Attention输出word、每个ACK前提交的score向量及max传递、相同Q/K/V地址、PackedRequest/Ack序列和ACK之后softmax/PV完整Scalar原语序列。另与未改OfficialAttentionOwner的独立原调度输出逐字比较。两条调度共享已有IEEE RNE原语参考，不声称另建了独立IEEE引擎。

正常M1：12 scores/12 groups，vector Add192、Mul12、BF24，scan192/add-stripe192/scale12/retire12事件。
正常M2：36 scores/24 groups，vector Add576、Mul36、BF72，scan384/add-stripe384/scale24/retire36事件。

每score移除的是原Python `_op` 的19次调用（16Add+1Mul+2BF）；真实旧Chisel mandatory Scalar算术请求是17，不把2次BF当硬件Scalar请求。计数均不是时钟或加速比例。

新增测试覆盖：默认off原事件序列相同；M2 later-key scan fault与earlier-key fold/scale fault的顺序退休；舍入边界、取消、±0、subnormal、BF dot溢出；tail1..16的work级访问隔离；ready回压、无效结果、abort、伪造/提前/跳key/replay拒绝与跨work互斥。tail3..16仅work单测，不是完整M16 Attention。DZ只注入flag验证fatal mask，不宣称有限Add/Mul实际产生DZ。

## 复现

在当前完整源码checkout：

    python -B candidates/qwen2_ordered_schedule/test_numeric.py --source-root . -v
    python -O -B candidates/qwen2_ordered_schedule/test_numeric.py --source-root . -v
    python -I -B candidates/qwen2_ordered_schedule/test_numeric.py --source-root . -v
    python -I -O -B candidates/qwen2_ordered_schedule/test_numeric.py --source-root . -v

审查时可用 `--selected-root` 指向只读已发布selected候选目录；默认同checkout。只加入自己的已解析目录并检查模块来源，不把生产root加入sys.path。全部原始数值输入源由旧harness的19-source pins复核。

纯source准备：

    python -I -B candidates/qwen2_ordered_schedule/prepare.py --source-root . --output NEW

要求新目录，先核旧schedule和新postimage。输出 `candidates/qwen2_resident_matrix/production_qk16_model/{schedule.py,ordered_work.py}` 和COMPOSITION记录，不能单独import成完整生产包。

每个测试进程限定1 CPU、CPU20秒、地址空间256MiB、wall25秒。无权重下载、无native编译/执行、无M16/M128、无elaboration/RTL或新CI dispatch。软件数值/工作协议通过也不能升级为全block或80%/90%结论。

## 本批结果与失败保留

normal、-O、-I、-I -O 各21项通过：11项新增generator/work测试，10项原numeric/source回归，共84项执行。validation保留各模式日志/hash和资源；source-only composer两文件逐字匹配、拒绝既有输出、输入漂移在创建输出前拒绝。

独审先发现并实际复现两个新增软件协议缺陷：末key在尚未退休时可伪造回复、最终回复未由generator消费前可提前启动下个work。均新增失败回归后修复，原失败日志hash及修复摘要在DEVELOPMENT_FAILURES.json。这些是新Python适配器缺陷，不是已测Chisel缺陷，历史失败未追认为PASS。
