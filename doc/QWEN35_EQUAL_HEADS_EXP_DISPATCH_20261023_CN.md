# PASS（显式策略门及原 owner Scalar 分派）/ INCOMPLETE（完整 block 数值与 RTL）

本批为 0.8B 的 EQUAL_HEADS 路径增加独立实验策略
EQUAL_HEADS_EXPERIMENTAL_EXP；实际运行只验证策略门和五个原始 FP32 输入的 Scalar
分派，不是完整 chunk、128-token prefill 或完整 block 验收。

## 接入范围与保持项

- chunk/exp_policy.py 新增明确命名的 opt-in，复用已有 DecayScalar 的
  exp_negative_ieee_rne。没有新增数学配方、数组、生产 opcode 或 Chisel 修改。
- 旧 IEEE_EXP 仍仅允许 GROUPED_35B，不因新策略自动允许 EQUAL_HEADS；新策略反向
  拒绝 GROUPED_35B。legacy exp、默认 Vector fatal30 保持不变。
- 新策略要求已启用 DecayScalar、显式 IEEE_POLICY 和一致的 fatal28。仅 schema 验证可
  不提供资源；真实 ChunkOwner 构造仍先拒绝空 Scalar/Vector，不由可选参数绕过资源门。
- operation/identity 对未知策略改为 fail-closed，不再把未知名字默认为 legacy。
- 新策略 identity 包含 helper 本身和复合 Scalar 来源 hash，明确 experimental=true、
  numerical_acceptance=null、full_block_validated=false、rtl_validated=false、
  production_new_opcode_bound=false。没有正确舍入或 Torch bitexact 声明。

TypedChunkDriver 在成功 terminal 前比较保存的 source_identity 与当前源码 hash，
运行资源 tuple 已包含 exp policy 和 enable_ieee_exp。它们不是通用运行时 callable
防篡改保证：Scalar op/_evaluate_exp 的运行时 callable 冻结仍有缺口。
full_driver 仍要求 exact PrepScalar，未接入本实验策略；不得把本批说成完整 block 已可用。
后续需先审查共享 Scalar callable/来源冻结，再决定 full_driver 显式选择接入。

## 根执行结果及精确证据层级

独立审查后，run_equal_heads_exp_bounded.py 实际 exit0，payload
0.13092971802689135 秒，peak RSS 28660 KiB，38 个文件 pin 前后一致，无 denied operation。

1. 四项 cold 测试全部成功，0 skip/error/failure：双向 layout 拒绝、enable/IEEE28 门、
   legacy 默认/operation、来源与否认验收字段；同时包含未知 helper 策略拒绝与 schema
   空资源允许/真实构造空资源拒绝。此阶段 audit 阻断所有 ctypes.dlopen，实际没有调用。
   stdlib ctypes 的当前进程 handle 初始化发生在 audit 安装前，明确不算 cold 阶段测得。
2. 原四项 range-contract 回归全部成功，0 skip/error/failure。包含整数 RNE 边界、15 输入
   Decimal 诊断、旧 GROUPED_35B gate、两次真实 R2 单 lane UF|NX 检查。数值容差仍未分配，
   不因为回归 unittest 成功而将 exp 数值 acceptance 从 null 改成 true。
3. 五输入使用真实原 ChunkOwner._exp → DecayScalar.op/_evaluate_exp，没有替换 owner、
   注入算术或 monkeypatch。输入为 c2a00000、c2aeac50、c2b72752、c2cff1b4、c2cff1b5；
   对应输出 05bfecba、007fffe6、0001d7fd、00000001、00000000。
   原同一 caller-owned Scalar 发出 5 次候选操作，内部 63 Mul、45 Add、5 integer RNE，
   3 次非正常输出、1 次零输出，旧 abs>=80 saturation 次数为 0。
   这些是软件操作计数，不是 RTL 周期、有效 MAC 或延迟实测。

第三阶段构造真实、已核验的 R2 Vector16，显式 fatal28，但没有执行 Vector 算术。
不能将第二阶段两次 native Mul 混称第三阶段 native chunk 运算，也不能将五词分派
称为完整 chunk/control/data path 验证。未运行官方 Torch、权重、完整 producer、block 或 RTL。

## 有界复现及公开内容

Runner 使用单 CPU affinity、512 MiB 地址空间、20 秒 CPU、25 秒 alarm；外层要求
GNU timeout 30 秒及 2 秒 KILL 宽限。audit 阻断网络、子进程，cold 阶段阻断全部动态加载，
后续只允许当前进程 None 和精确已核验 R2 ELF。无编译、下载或重跑完整 M128。
这是 Python audit 层限制，不是任意原生代码安全沙箱证明。38 文件 pin 不宣称涵盖整个
安装 Python/NumPy 环境闭包。编译器 hash 仅沿用 build receipt 身份，未执行编译。

公开摘要：reports/execution/QWEN35_EQUAL_HEADS_EXP_DISPATCH_20261023/summary.json。
保留相对源码 pin、外部角色 hash、五个固定诊断词和 raw result/log hash。私有绝对路径
manifest、raw result/log 与任何权重不提交。既有 range-contract 私有 manifest 保持不动。

在已具备 NumPy、已验证 R2 ELF/receipt 的环境中，将摘要相对 source_pins 与已审核的
external_role_sha256 映射到当地文件。审核匹配后准备本地 manifest，字段为 files、
native_library、interpreter_sha256、pin_scope；不能无条件接受当前文件 hash。环境不同
应记新运行身份，不宣称 exact native pin 复现。准备全新输出目录，在仓库根目录运行：

    timeout -k 2s 30s <python> -B candidates/qwen35_gdn_prefill/chunk/run_equal_heads_exp_bounded.py --pins <private-pins.json> --out <new-local-output>

核验 cold4/range4 均无 skip/error/failure、五词分派完成、pin 不变、无 denied 与 exit0。
保留所有未通过记录，不能放宽数值容差换取 PASS。本批 done 仅指策略/分派小门；完整
官方输入 block 数值、共享 Scalar callable guard、Chisel 绑定与同刺激 RTL 回放仍待完成。
