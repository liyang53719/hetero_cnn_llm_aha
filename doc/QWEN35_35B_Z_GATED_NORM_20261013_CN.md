# 35B L0 Z 与32头 gated RMSNorm 接线

## 范围和计划

- 已发布依赖 fb377c5b：同次真实前缀到全32头chunk，M16/M128均完成实际执行和同输入诊断；三条原CI及原ZIP已闭环。
- 本批继续同一个TypedMemory、Matrix4096、Vector16及一个GateScalar。Z从该次实际RMS输出投影，不从留存raw伪造生产者。
- chunk成功、完整写入/ACK、终态接收并排空后，只发布core中间张量。state、scratch和Conv history保持private，不推进generation，不代表完整block提交。
- gatednorm同时消费该次真实core和Z，32头×128维，gamma保持原F32[128]。
- O的K4096投影、残差及MoE、联合状态提交仍待后续；本批不下载O或专家。

## 已完成的依赖证据

- 按原模型revision及shard13/14 header固定身份，取得Z BF16[4096,2048] 16,777,216 B及norm F32[128] 512 B。仅本地ignored work保存，Git不提交权重、raw或其文本编码。
- 新独立参考执行原35B完整N4096 Linear及原reshape。严格C独立实现sequential与两K1024 high-first，各partial FP32、一次FP32 merge、最终BF16 RNE；拒绝非RNE和FTZ/DAZ。
- M16/M128新N4096配方均与原官方输出逐bit一致；sequential分别13/77处bit差，max4ULP，maxabs0.015625/0.03125。原N8192和N32结果未代替本校准。
- Z官方范围M16 [-17.125,8.3125]、M128 [-17.125,8.9375]，未踩现gatednorm负域限制。
- 官方norm原类及SiLUActivation/ClassInstantier保持固定AST。完整forward实际观察12节点，包括square、mean、eps、rsqrt、归一化第一次BF16、F32 gamma、F32 SiLU和最终BF16。去掉可选hub decorator的边界明确。
- 小合成原forward smoke3个case与无观察版逐bit相同；8项Torch-free参考测试通过。尚不代表真实norm数值通过。

## 资源与精度边界

- 32头布局每token8192B，128F32 head cache及128F32 gamma cache不扩为整32头缓存；gate仍逐64B流入。
- norm读512+2×M×8192B、写M×8192B；M16预期读262656/写131072，M128读2097664/写1048576。以上为闭式预测，已与下文两档实际runner计数核对。
- Z的N4096分26个窗口（25×160+96），原5个context及共享资源；M16物理pad128必须计入执行MAC，不能按16token当满利用率。
- 当前norm仍旧ascending FP32、sqrt后reciprocal及原SiLU近似。没有给独立norm新增误差阈值；先保存实际输出与官方各中间值诊断。
- 生产Chisel32头布局、完整算术绑定、generator驻留上界、完整硬件周期及MAC利用率/占空比仍open。软件请求/ticks不当硬件周期。

## todo / ongoing / done

- done：payload范围/身份校验；独立N4096两档校准；32头norm布局和原16头回归；原官方12节点参考。
- done：core-only发布后read/末ACK故障保护；同次真实M16、M128的Z与norm接线运行。
- done：两档冻结源/raw独审与中文摘要。
- ongoing：小批发布与精确CI闭环。
- todo：O的K4096独立校准及后继完整block。

## M16实际完成

- 同次十个owner终态成功：RMS、QKV、Conv、A、B、pack、Prep、Z、chunk、gatednorm。85个执行源和12个native/固定来源记录前后不变。
- 之前chunk批的全部上游输出、state和scratch逐SHA相同；新Z实际输出与独立C及官方全N4096逐bit一致。
- norm完整65,536个BF16词，1处bit差，max1ULP、maxabs1.52587890625e-5、mean2.3283064365386963e-10。未新增standalone门，仍是同输入诊断。
- norm实际读262,656 B、写131,072 B、4,104次读/2,048次ACK、12,305软件transport ticks；657,408次Scalar请求。资源和周期层级不混用。
- 仅core中间发布；2MiB state、完整scratch、Conv history保持private，generation为0。
- 唯一输出差异在token2/head25/lane121。独立固定配方重放该128维head逐字节复现实际输出；第一次BF16归一化与官方相同，SiLU约2个FP32 ULP差把最终乘积推到BF16舍入中点，形成1个BF16 ULP差。这是有界独立配方归因，不冒充actual owner中间值观察，也不为此新增资源或误差门。

## 本地回归和取证记录

- 干净冷回归583项/59套/176源，零skip、前后不变；中文计划清单91项。
- 首轮583项/59套各suite均通过，但source快照漂移，整体明确FAILED。原因是合成smoke三份identity及raw最初输出在源目录，发现后全部移入ignored work并修正输出路径；无raw提交Git。保存失败日志，并以上述干净整轮重测替代，未复用该轮PASS。
- core-only发布边界测试以脚本化chunk算术驱动真实30,146,560 B写/ACK；随后真实norm读错/末ACK错均不提交state/history。这个测试证明事务隔离，不称checkpoint chunk数值。
- scripts/diagnose_qwen35_norm_first_difference.py仅对留存输出做有界独立配方重放；普通/优化Python产生相同摘要，错误summary pin在优化模式也拒绝。

## MAC计数口径

两档均已由真实终态计数逐字段核对；不以shape公式替代C++执行计数。

- 新Z M16有效134,217,728 MAC，实际执行1,073,741,824 FMA；M128有效与执行均1,073,741,824。保留M16物理128行padding，尾窗实际96列，52个K partial。
- 包含QKV/A/B/Z的Matrix总执行两档均3,238,002,688 FMA；M16有效404,750,336，M128有效3,238,002,688。对应12.5%/100%只是有效工作量除执行工作量，缺少完整周期，不能称MAC利用率。
- chunk Vector另计M16有效27,754,496/执行167,510,016，M128有效284,950,528/执行335,020,032个独立Mul→Add lane对，不当FMA。norm的平方归约各65,536/524,288个独立Scalar乘加对另列。
- 全block周期、busy duty、active-lane duty、target-memory stalls和真实流水重叠仍未知；本批没有90%或80%达成声明。


## M128实际完成

- 同一冻结85源/12native，十个真实终态全部成功。上批完整chunk的全部输出、state和scratch逐SHA相同，新Z与官方及独立C逐字节一致。
- 完整524,288个BF16 norm词，15处bit差，max1ULP、maxabs3.0517578125e-5、mean2.2214408090803772e-10，全部finite。报告保留全部12个原forward参考中间值hash；没有新设norm误差门或完整blockPASS。
- norm实际读2,097,664 B（32,776次read）、写1,048,576 B（16,384次ACK），98,321软件transport ticks；5,259,264次Scalar请求。
- Matrix累计160次真实acquire/release和dense_done，3,238,002,688次C++ FMA；原5context及16×1376 bank ledger不变。
- core中间发布成功，state/scratch/history的hash及private身份未变；最终block联合提交仍未实现。
- 两档host walltime受到冷回归并行影响，不做性能前后对比。所有算法useful/executed计数与完整硬件周期层级分开。

## 可复现交付

- payload.py 提供固定revision/header/206范围的plan、collect、verify；仅Z和norm参数。
- z_reference.py 固定原fullN4096 AST，分别生成M16/M128独立C与官方诊断，保留FP环境、自测和完整编译来源。
- scripts/run_qwen35_35b_gated_norm_diagnostic.sh 接受QKV/N32/N4096三个独立报告及其SHA、新输出目录；每次从实际RMS重新执行，不读参考raw伪造producer。
- reports/execution/QWEN35_35B_Z_GATED_NORM_20261013.json 保存各层证据、计数和边界；所有原raw、权重和binary留在ignored work，Git仅脚本/源码/pin/hash/摘要。
