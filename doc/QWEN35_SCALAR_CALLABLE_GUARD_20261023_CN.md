# PASS（Scalar callable 身份小门）/ UNKNOWN（完整数值）/ RTL 0/5

本批只收紧现有 Qwen3.5-0.8B FullBlockCoordinator 的共享 Scalar 身份检查。
不接入完整 block 的实验 exp 选择，不改变 Prep/Chunk 默认策略，不改变 Vector
默认 fatal30、生产 opcode、Scala/Chisel 或物理算术资源。完整 block 数值保持
UNKNOWN，RTL 保持 0/5；下面的 guard 测试不是模型验收。

## 可复核改动

- 新增 scalar_identity.py，在模块导入时保留既有 SharedScalar → ConvScalar →
  PrepScalar 的原始类、MRO/父类、每一层 op，以及 acquire/release/_exp_node/
  _soft_node 的函数、code/defaults/closure 身份。实例方法覆盖、继承链重绑定和
  原函数对象上的 code 修改均在检查边界拒绝，不能在 coordinator admission 时
  把已经被修改的方法重新登记为合法基线。
- 逐一检查三个模块自己的数值 helper 别名、系数/常量、NumPy 原语及 struct
  pack/unpack 绑定。Scalar 计数器和正常 lease client 的演进不视为身份变化。
- 独立 guard 可以检查 DecayScalar 的 op/_node/_evaluate_exp 及显式 enable 标志；
  这只是已有候选的身份准备。FullBlockCoordinator 仍只接受 exact PrepScalar 且
  enable_softplus is True，明确拒绝 DecayScalar 及任意子类；整数 1 不能冒充 True。
- coordinator 资源身份纳入 Scalar guard、实际 chunk.ep 模块别名和 operation
  路由函数，以及 chunk.exp_policy/layout、prep.layout/gate_policy/reduction_policy。
  admission、start/tick、owner callback 返回后、最终 report 均重新核验。
- freeze_identity 记录同一个真实 Scalar 的配置，快照加入 guard、exp_policy、
  layout/reduction 和 Scalar 来源；run 将这个同一实例交给 coordinator，最终
  report 必须与 prelaunch Scalar 配置一致。无新的 Scalar 算术资源。

## 最终提交围栏不被检查拆开

非最终 tick 在 owner 返回后检查身份，即使它尚无 terminal 也不能悄悄带着改写后的
Scalar 返回。最终成功路径保持原顺序：preflight → owner 接受 held terminal →
joint commit；不在 output 已发布而 history/state/roots 尚未共同提交的窗口插入
新可失败检查。新检查在 joint commit 之后、最终报告之前执行。

观察者在最终提交之后改写 Scalar 会使检查和 report 失败，但不声称回滚已经完成的
软件提交。run 的既有异常分支会保留 FAILED 摘要，不产生成功 actual_terminal。
相应对抗测试检查最终输出、history/state 和 generation 不会被新增检查拆成半提交。

## 检查的限制

这不是敌对 Python 进程的安全沙箱，不证明磁盘源与已经载入的 bytecode 等价；不覆盖
模块首次导入之前的改写，也不能发现同一同步 callback 内先改写、使用再恢复的行为。
不全面冻结任意 owner 方法、外部 Python/NumPy 安装或所有原生执行。SharedScalar 的
FE_TONEAREST/渐进下溢检查仍仅在构造时进行，本批不新增运行中 FP 环境复核。

检查本身不执行 Scalar 算术、不重复加载库、不逐 tick 读取来源文件；会增加软件检查
开销，尚未测量完整任务开销，不能换算为 RTL 周期、延迟或 MAC 利用率。

## 有界测试计划与证据分层

1. cold Scalar：裸对象和对抗性方法/常量/别名/标志变更，不运行数值 Scalar。
2. synthetic coordinator：真实 TypedMemory 写入/ACK/发布和 coordinator 控制；
   所有数值 owner transport 都是明确的模拟对象，不能称为真实完整层运行。
3. 原 Vector backend admission 与 equal-head exp policy cold 回归，无 native 算术。
4. actual Scalar：真实 PrepScalar 8 次小操作与 DecayScalar 原五个原始词诊断，共
   13 次 public Scalar 操作；没有注入算术结果，也没有 Vector/Matrix、权重、Torch、
   chunk/full-block 或 RTL 执行。五词相等仅为诊断回归，不分配新的 exp 精度容差。

run_scalar_identity_bounded.py 使用单 CPU affinity、512 MiB 地址空间、50 秒 CPU、
55 秒 alarm，外部要求 GNU timeout -k 2s 60s。audit 禁止网络和子进程；cold 阶段禁止
全部 ctypes.dlopen，actual Scalar 阶段只允许当前进程 None。stdlib ctypes 当前进程
handle 初始化在 audit 前，不能算作 cold 阶段测得。Python audit 不是原生安全沙箱。

本地预审 manifest 固定来源与解释器；执行前后比较，且实际载入的仓库 Python 文件
必须全部有 pin。闭包包含静态 imports 和已识别的字面量动态导入来源，不声称覆盖
整个已安装 Python/NumPy。manifest 的环境路径保持私有，不提交。

执行命令（替换为已核对的解释器、私有 pins 和全新本地输出目录）：

    timeout -k 2s 60s <python> -B candidates/qwen35_gdn_prefill/run_scalar_identity_bounded.py --pins <private-pins.json> --out <new-output>

## 实际执行和失败保留

经独立源码审查，修复后实际执行一次有界测试。attempt2 exit0，payload
29.50910126202507 秒，peak RSS 227284 KiB；89 项测试全部成功，0 skip/error/failure：
9 cold Scalar、57 synthetic coordinator/receipt、17 Vector backend admission、
4 equal-head policy、2 actual Scalar。101 项来源 pin 前后一致，实际载入的仓库
Python 来源全部在 pin 中，denied operations 为 0。仅 actual Scalar 阶段发生
3 次 ctypes.CDLL(None)，无 native Vector/Matrix 动态库加载或算术执行。

先前 attempt1 保留为 FAILED：0.1461305320262909 秒，cold Scalar 共 9 项，
5 error，后续阶段 NOT RUN。首个错误来自测试自身用 mock.patch 修改函数
__code__，清理时尝试 delattr 导致 TypeError，并留下 word helper 的修改；后面
4 项被生产 guard 正确拒绝。修复仅更换测试的函数 descriptor 恢复方式：保存原值，
try/finally 显式 setattr 恢复，再核验 guard。没有放宽生产检查、跳过用例或改动容差。
两次的来源/日志 hash 与失败原因均保留，不能只保留成功一次。

公开摘要：reports/execution/QWEN35_SCALAR_CALLABLE_GUARD_20261023/summary.json。
摘要含仓库相对 source pins、解释器角色 hash、两次实际退出/分层结果、资源上界和
raw result/log hash，不含私有绝对路径、完整日志、权重或任何新模型输出。

此 PASS 只表示身份/配置控制及既有小样本 Scalar 回归通过。完整官方输入 block 的
数值验收仍 UNKNOWN，RTL 0/5，运行中 FP 环境仍未复核。后续必须另审实验 exp 的
显式接入与对应 provenance，不能因本批成功自动放宽 full_driver。
