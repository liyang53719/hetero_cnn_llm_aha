# PASS（显式 full_driver 策略/控制及十次 Scalar 分派）/ UNKNOWN（完整数值）/ RTL 0/5

本批完成 0.8B EQUAL_HEADS 显式软件策略接线，并经独立源码审查后实际执行一次有界测试。
未运行完整 chunk、官方输入 block、模型、PyTorch reference、Scala/Chisel 或 RTL；
不引入新算术配方、生产 opcode、物理资源、数值容差或吞吐结论。

## 接线及保持项

- FullBlockCoordinator、run、CLI 和 freeze_identity 增加 chunk_exp_policy，默认仍为
  LEGACY_EXP。只接收该旧策略或 EQUAL_HEADS_EXPERIMENTAL_EXP；旧 GROUPED_35B 专用
  IEEE_EXP、未知名称均拒绝。CLI 不自动改选 Vector policy、backend 或 projection。
- 旧策略仍要求 exact PrepScalar 且 enable_softplus is True。实验策略要求 exact
  DecayScalar、两个 enable 标志都为字面量 True、显式 IEEE Vector 和整数 fatal28。
  GateScalar、任何子类、整数 1 冒充 True 均拒绝。
- run 只创建一个所选 Scalar，原样交给 freeze_identity 和 coordinator；全部原 owner
  共用它。原 ChunkOwner 与实际 ChunkJob 均收到同一显式 exp policy，没有旁路 compute。
- Prep gate/reduction、chunk cumsum/matmul、RMS、projection 与 Vector backend 默认不变。
  新实验策略只是 chunk exp 分派；Prep 仍使用原策略，不连带改成 35B gate。

## 身份与提交围栏

原 ScalarIdentityGuard 覆盖所选 Scalar 的继承链、方法、数值 helper 与字面量 flags。
新增 import-anchored 检查覆盖 exp operation/validate_policy/identity、相关策略常量和
模块别名、POLICY_MASKS 的对象与带类型内容、layout 内容，以及原 ChunkOwner._exp
函数/代码及实例 bound method。共享资源 tuple 同时冻结 coordinator/owner exp 选择、
chunk cumsum/matmul 和既有 Prep 策略。每个边界只检查一次该 dispatch 路由。

检查边界仍为 admission/start/tick、非最终 owner callback 返回后、observer 返回后、
最终提交前和 report。最终 owner 接受 → history/state/output joint commit 之间没有
新增可失败检查。提交后的 callback 变更会使成功报告失败，不宣称回滚已提交的 roots。
per-tick 检查不读取来源；来源 hash 仍在 snapshot/report/原终端路径和 final_identity。
这些不是任意 Python 防篡改沙箱：不覆盖首次导入前改写、同一同步 callback 内改写后恢复、
所有 owner 方法或外部原生环境，也不证明磁盘来源等于载入 bytecode；运行中 FP 环境
仍未重检。不得把 host 身份检查开销换算为 RTL 周期或 MAC 利用率。

报告和 snapshot 显式使用 arithmetic_seal_schema=qwen35_full_arithmetic_selection_v2，
包含 exp profile、Scalar binding、cumsum/matmul 与既有 Vector backend。run 最终检查
一致性；full_compare 要求相同冻结字段、对应最终检查标志和合法的 policy/Scalar/IEEE28
组合。实验 profile 的 numerical_acceptance=null、full_block_validated=false 和
rtl_validated=false 不因控制测试而改变。

历史缺少 v2 字段的 seal 会 fail closed。不能给旧报告补字段、改名或追认 v2；如需当前
比较入口接受，必须另审并重新执行/核验产生新完整证据。旧文件与历史结果保持原状。
所有既有数值阈值、比较公式、BF16 domain 与冻结 gate source hash 保持不变。

## 已执行的有界测试及精确覆盖

新增 run_full_driver_exp_bounded.py。限制为 1 CPU affinity、512 MiB 地址空间、
50 秒 CPU、55 秒 alarm，外部 GNU timeout -k 2s 60s。禁止网络和子进程；cold 和
synthetic 阶段禁止全部 ctypes.dlopen，实际 Scalar 阶段仅允许当前进程 None。
stdlib ctypes 当前进程 handle 初始化在 audit 前，不算 cold 阶段测得。Python audit
不是原生安全沙箱；source pin 不声称覆盖全部 Python/NumPy 安装。

分层覆盖：

1. cold Scalar guard 旧回归；新策略 exact type/flags/IEEE28/unknown/grouped 拒绝，
   helper/code/alias/mask-content/owner._exp 改写拒绝，以及 CLI 默认与显式传参。
2. run 入口使用明确模拟 snapshot/coordinator，检查一个 Scalar 实例同时进入两处；
   此项只证明传参，不能称为真实 run 或 freeze_identity I/O 执行。
3. 既有 57 项 synthetic coordinator/receipt 回归与新实验策略控制：真实 TypedMemory
   写入、ACK、发布、cold/carried root 与 joint fence；所有数值 owner transport 模拟。
   原 driver constructor 验证会执行，但 owner admission/service acquisition 明确模拟。
4. full_compare 的合成文件 seal 与原阈值回归；不是实际模型输出，不读 Torch reference。
5. 原 Vector backend admission 与 equal-head policy cold 回归。
6. actual Scalar：构造 coordinator 所选真实 Scalar 和真实 ChunkOwner，使用明确模拟
   Matrix/Vector handle、零占位参数，未启动任何窗口。原 owner._exp 直达同一个 Scalar，
   legacy 与实验各五个固定原始词，总共十次 public exp 操作；无 Vector/Matrix 算术。
   实验五词对应原记录输出及 63 Mul/45 Add/5 integer RNE，仅为诊断回归，非 exp 精度门。

来源 pin 必须预审，执行前后相同，且实际载入仓库 Python 来源全部在 pin 中；pins、
原始日志和结果使用全新私有目录，保留所有失败。不得使用或改动既有私有 attempt1.pins。
复现前须先审核当前来源与解释器是否对应已执行 pin，不可无条件重封当前文件。
下面只给可移植命令模板；解释器、私有 manifest 与全新输出目录须先核验：

    timeout -k 2s 60s <python> -B candidates/qwen35_gdn_prefill/run_full_driver_exp_bounded.py --pins <reviewed-private-pins.json> --out <new-private-output>

## 根执行结果与公开证据

attempt1 实际 exit0，payload 38.559589619981125 秒，peak RSS 235060 KiB。
9 个阶段合计 144 项全部成功，0 skip/error/failure：cold Scalar 9、新 admission 6、
legacy synthetic control 57、实验 synthetic control 11、synthetic comparison seal 38、
Vector backend cold 17、equal-head policy cold 4、actual legacy/实验 Scalar 各 1。
两个 actual Scalar 测试共十次原 public exp 操作，未启动任何 coordinator window。

144 项来源 pin 执行前后及归档时一致，实际载入的 72 个仓库 Python 来源均有 pin。
无 denied operation；audit 后仅 actual Scalar 阶段发生 3 次 CDLL(None)，无 native
Vector/Matrix 库加载、算术、编译或网络。新进程中各段按阶段检查，不把 cold 控制、
合成数值 transport、十次真实 Scalar 分派混称完整计算链运行。

公开摘要为 reports/execution/QWEN35_FULL_DRIVER_EXP_POLICY_20261023/summary.json，
只包含仓库相对 source pins、解释器角色 hash、分层结果、资源上界及 raw result/log hash。
不包含私有绝对路径、原日志、原始数组、权重或新模型输出；私有 manifest 与全部历史
证据保持原状。执行后的源码未改动，文档及安全摘要单独整理。

此 PASS 只关闭策略接线、身份/控制门和固定 Scalar 诊断回归；完整官方输入 block 数值
仍 UNKNOWN，RTL 0/5，无硬件周期或 MAC 利用率达标证据。下一步需单独审核显式策略
在真实 producer、全 head、双 chunk 及完整 block 中的数值/中间值与调度覆盖，不能因
本小门通过自动运行完整 block、改变容差或追认历史 seal。当前发布仍待独立批准。
