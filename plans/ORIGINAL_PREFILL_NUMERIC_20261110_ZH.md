# 原 Chisel prefill phase1–5 连贯数值推进（2026-11-10）

## 边界和基线

已核远端 main `dcc0480c37cf548d6c10ce22087090e92a3ddbce`。原本地 `90b91a63` 的未发布候选保持独立，本批不会夹带发布。五块统一硬件目标保持 4096 Matrix MAC、8×512、Vector32，不改生产算术、容差或资源参数。五块完整原 Chisel M128/真实权重仍 **0/5**。

上轮通过的两个 legacy runtime16 phase1、两个 guarded runtime32 phase1 及 88 个 exp 原语案例不重跑。本轮新增 native 后端、完整单头单 chunk phase2，以及有真实 receipt 和内存连续性的 phase2→3/4 集成。新集成执行相同运算是验证真实前后级交接，不是重复提交已通过的独立测试。

## 实际数值与执行成本

`candidates/original_native_backend_20261110/` 保存官方 Debian Verilator 5.032 的来源、包哈希、115 个运行文件哈希及本地恢复脚本。只恢复至任务本地目录，不全局安装。原 `HeteroFP32Alu` 的 4,096 个有限 dyadic Add/Mul 数值及异常标志检查通过，native 循环 0.119 秒。此小例只证明后端可用，不证明 phase2、完整矩阵或物理资源。

`candidates/original_derived_pair_numeric_20261110/` 将未改动的原 `GdnRuntimeChunkDerivedAndPairV2Owner` 接真实 `BlockScalarFloatPolicyV2`、原 `UnifiedVectorElement32BankV4` 与 HardFloat。head0/chunk0、runtime16/legacy 的 2,816 个写拍（45,056 个 FP32 字）逐位匹配，3,681 读拍、2,209 exp、2,144 vector add、2,560 vector mul 的请求/返回计数完整匹配。decay 数值、context/layout/head/chunk/numeric 身份、receipt 及 held-done 检查通过。66,582 cycles，native 循环 1.002 秒，native elaboration/build/run 合计 31.51 秒；Scala 编译另计 13.25 秒。

该 phase2 单例最初的 Treadle 校准在第一个 100-cycle 检查点之前触发 90 CPU 秒限制，不继承任何数值通过。第一次 native 在仿真前因 GCC PCH 头文件顺序失败。保留两次历史源码与摘要，仅用 `MAKEFLAGS=VK_PCH_I_FAST= VK_PCH_I_SLOW=` 取消 PCH include 优化解决，生成 C++ 的普通头文件仍正常包含，原电路没有变化。

`candidates/original_derived_transpose_chain_20261110/` 一次 native 集成通过。phase2 的实际完整 result 通过硬件握手直接进入原 transpose owner，未制造 phase2 receipt。保留同一内存中实际接受的写值，512 个 KE 写拍逐一验证后续读取来源；没有阶段间注入 oracle 结果。新增 phase3 KT、phase4 KET 的 1,024 写拍逐位匹配，整链合计 4,705 读拍、3,840 写拍、61,440 个 FP32 字、70,679 cycles。native 循环 1.211 秒，native 阶段 36.34 秒；Scala 编译另计 13.91 秒。phase1 仍是该单独目录的明确合成前提。

## 验证资格

`candidates/original_loadprep_to4_chain_20261110/` 进一步移除合成 phase1 receipt 和预填 scratch 前提。原 LoadPrep 与 Derived 共用同一个真实原 scalar，整个链只实例化同一个原 32-bank；phase1 的实际 result 直接进入 phase2。单一内存最初只含 synthetic prepared-input，不含 scratch。第一、第二个真实交接分别在 6,593 和 73,176 cycles，且所有实际内存确认均已排空。下游读 scratch 必须有前序实际接受写的来源。最终 **6,305 读拍、5,440 写拍、87,040 个 FP32 字全部逐位匹配，77,272 cycles**。phase1 的 64 次 Add、phase2 全部运算计数与 decay、phase3/4 receipt、保持完成输出检查均通过。一次 native 完成，循环 1.565 秒，native 阶段 36.38 秒，Scala 编译另计 13.10 秒。超出 cycle 上限会明确失败，不以部分执行返回成功。

这个1→4集成不再伪造 phase1 或 phase2 的前后级交接；prepared-input producer 和初始 state receipt 仍是明确 synthetic 前提。未覆盖的是从真实模型输入产生 prepared Q/K/V/gate/beta、真实初始状态来源及后续 phase5–17，而不是把这些前提当作已执行。

以上均是原 owner 和真实算术，不是软件数值 responder。测试使用一次性顺序调度和低 16 lane 客户端适配，不是生产共享 authority/router。原 32-lane bank 源码未变，上 16 lane 填 +0 可能被优化掉，因此不能据此宣称物理 Vector32 或 4096 MAC 分配已验证。输入来自固定 synthetic 生成器，不含训练权重。FP32 oracle 按原 scalar source order 每节点舍入，原 approximate exp 不等于 correctly-rounded exp 或 Torch 完全相等。

固定输入的 Q/K 在坐标 0、17、63、127 上有稀疏非零值，每行 V 为确定性密集值，跨越 16/32-lane 边界。全部输出字比较包含零填充；这不是密集随机、全部 FP32 特殊值或训练分布的穷尽测试。

完整 M128 需要剩余矩阵/solve/state/output 阶段、多个 head 与两个 chunk，以及真实 producer/state/权重闭环。当前没有完整块性能、MAC 利用率、最终 RTL、综合、时序或 QoR 新通过。

## 继续接原默认 phase5：UT 数值和真实前序来源通过

已逐字核原 fresh-top 的 `GdnRuntimeChunkLeafCollection` 默认使用 `GdnRuntimeChunkExecuteOwnerV8`。其 phase5 执行 `KB(64×128) × KT(128×64)` 后逐元素乘 Pair，走 ordinary16-client→原 source32 bank，并非 4096-MAC MatrixPipeline。没有擅自切换到 opt-in ExecuteOwner32，也没有以 Vector 运算通过冒充 MatrixPipeline 或整块资源验证。

`candidates/original_loadprep_to5_chain_20261110/` 把原 phase1–4 链继续接入未改动的 V8。phase4 实际 receipt、decay context/layout 直接进入 phase5；所有 phase5 读取地址均必须属于 phase4 交接时冻结的真实前序写入集合。一个 scalar、一个原 32-bank 按阶段共用，不以额外复制算术提升容量。期望 UT 由独立 ascending-K、每步 FP32 Mul 后 Add、最后乘 Pair 生成，不用软件响应硬件运算。

第一次有界 native 集成通过：phase5 新增 **35,072 读拍、256 UT 写拍（4,096 字）、65,792 vector 请求及返回、202,240 cycles**。全链 **41,377 读拍、5,696 写拍、91,136 个 FP32 输出字逐位匹配，279,513 cycles**。三个交接点 6,593 / 73,176 / 77,273 cycles，receipt/drained/context/layout/decay、计数、真实内存来源及 held-done 全部通过。native 循环 4.891 秒，native elaboration/build/run 45.41 秒，Scala 编译另计 17.42 秒，无失败或重跑。

这一最新目录已覆盖 phase5；前述独立1→4目录仍只宣称其实际执行的范围。完整五块保持 **0/5**。下一步沿默认 V8 接实际 phase6 及后续 solve/state/output，保持同一物理资源目标与真实前后级来源；多头/两个chunk、其他policy、真实 prepared producer/state/权重和完整 Host 仍需独立闭环。下一阶段代码依赖已可获得，不把“尚未执行”误称成工具拒绝或已有通过。

## 复现和运行保护

只发布原源码、测试适配/生成器、官方依赖 pin、hash 和精简摘要。TSV 刺激/实际内存、生成数组、JAR/class/工具二进制、IR/RTL、原始日志和权重/NPZ 留在本地，不进入 Git 或持久恢复包。各测试单独记录源码和运行身份，有独立进程组、240 墙秒上限、单编译任务和有限 JVM heap，超时仅回收自己启动的组。

当前资源够用，没有删除唯一证据或运行中引用文件。旧 PID 40532 仍为 EXIT_UNKNOWN，未重启、未释放保留。当前命令只看到局部进程命名空间，不以未见进程断言旧任务退出。没有触及 Voyager，也没有新开完整 Host/EDA 或重复重型 CI。
