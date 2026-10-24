# PASS（结构小门）/ INCOMPLETE（exp 数值验收）：既有范围合同审计

状态：实际执行 4 项结构/诊断测试通过，0 skip；exp 数值验收仍未分配容差。
不是 exp 数值验收 PASS，也不是完整 block 或 RTL 通过。
本批不修改现有 exp、GROUPED_35B 限制、Vector 默认 fatal30 或生产 Chisel。

## 限制位于哪里

- BlockFloat.scala 的 expScale（90–91 行）在 abs(x)>=80 时归零；expFinish（97 行）
  以正常数指数编码构造缩放。conv/scalar.py（58–69 行）复现这个项目合同。
  不能只删 80 guard，因为 k>=127 时原缩放编码不能表达所需渐进下溢。
- prep/scalar.py（51–66 行）另有 Softplus 负输入范围限制，本批不修改它。
- 官方 0.8B modeling_qwen3_5.py（327–330、364–405 行）先转 FP32，再 cumsum/exp；
  35B modeling_qwen3_5_moe.py（295–298、332–373 行）同样不含 abs>=80 截断。
  这是项目算术/适配限制，不是官方上游整体缺少 prefill。
- FP32/BF16 最小正常数均为 2^-126；最小非正常数分别为 2^-149、2^-133。
  RNE 归零半间隔分别是 2^-150、2^-134。exp(-80) 仍为正常数，提前截断不能用
  BF16 最终输出精度解释；chunk 内部官方算术本身是 FP32。

## 已有候选，不重复实现

candidates/qwen35_35b_exp/scalar.py 的 DecayScalar 已提供显式启用的 P7 候选。
47–71 行采用 RNE 整数范围归约、split-ln2、两段缩放，abs>=104 的保守零 guard。
普通路径 12 Mul+9 Add+1 整数舍入，非正常范围路径 13 Mul+9 Add+1 整数舍入。
旧非截断路径为 9 Mul+8 Add+1 截断整数转换。这些是算术节点，不是实测时钟。
候选可以作为单 ALU 复用设计起点，但 FSM、寄存器、握手和生产 opcode 尚无绑定；
不能据此宣称无延迟代价、必须大改或已达到 80%/90% MAC 利用率。

chunk/exp_policy.py（18–24 行）有意只接 GROUPED_35B、显式启用 Scalar 和 IEEE Vector。
既有测试明确拒绝 EQUAL_HEADS。没有找到可据以自动放宽的资格证明，本批保持拒绝。
该限制是当前资格范围，而非 exp 数学只适用于 35B 的结论。

R2 后端与 exception policy 是独立选择：R2 修有限 Mul 的 UF 判定，不改变默认 fatal30。
真实 UF|NX=3 仍被 fatal30 拒绝；显式 fatal28 接受有限渐进下溢，但仍拒绝 NV/DZ/OF。
不能把 R2 合格等同于完整 IEEE exp 路径已绑定生产硬件。

## 来源与历史证据边界

- 0.8B Transformers pin：14e738b5d0cc69aa27a95dde272aea41fde44f2f；源 SHA256：
  aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18。
- 35B Transformers pin：42ca97014c85d71a88ad60d55f08cb9fb4d26e2c；源 SHA256：
  ea77a3979cb659dd04dc1f6a1cd7d3df53ddc5759e40eb0d5e98846e95b39d30。
  模型 revision：62704185bd97ad488cfc404e7caea797396b74dc。
- DecayScalar SHA256：5e8f44c7a9ab95d9b18fff2fe443b4cc8742b0f037b61ff12121f6ba12c2e8c5。
- BlockFloat.scala SHA256：9863718ca90089bf812eb07dbd82ce16d982a8c74b04d7543de1bd2dfb1e37b5。
- 历史 EXP_DOMAIN.json 记录 70688 次调用、4705 次截断、1618 个官方非零被丢弃，
  最大丢弃值 1.7745667083182273e-35。摘要没有 normal/subnormal 数量拆分。
  这是已保存的 20261012 诊断，不是本批复现，不继承缺失原件的候选 PASS。
- 历史 35B 20261013 chunk exp 重放 M128 有 141376 个输入、4476 处差 1 ULP，
  旧误归零 918、新误归零 0。其 passed/thresholds=null，不是完整 producer/chunk。
  另有 32 头 M1 缩维零 QKV 控制门，不是 checkpoint 完整 block 验收。

## 本批小门及实际执行

新增 test_range_contract.py，只复用已存在且通过源/ELF/receipt 核验的 R2 库。
必须显式提供 GDN_VECTOR16_R2_LIBRARY；缺失即报错，不 skip，不自动编译。
不导入 Torch，不下载，不运行 owner，不生成 RTL。

1. 用整数 RNE 转换测试半最小非正常数、ties-even 和跨最小正常数进位。
2. 对 -80、正常/非正常边界、零边界及 -104 的相邻 FP32 原始词，加三个零附近输入，
   共 15 个输入。Decimal.exp 100/180 位交叉检查后用整数 RNE 转 FP32，打印候选与旧实现。
   这是高精度参考稳定性检查，不是 interval 证明或官方 Torch 新结果。
   ULP 仅诊断；没有已分配容差，因此数值 passed/thresholds 保持 null。
3. 用真实 validate_policy 验证已有 GROUPED_35B admission、EQUAL_HEADS 拒绝、
   未启用 Scalar 拒绝和 legacy Vector 拒绝；不扩展资格范围。
4. 两次单 lane R2 Mul 以 half-minsub 验证真实 UF|NX：默认 fatal30 拒绝，显式28保留结果。

经独立源码审查后实际运行，4 项 unittest 用时 0.012 秒，payload 0.16832947701914236 秒，
退出 0、0 skip、0 denied operation，32 项前后 pin 一致，peak RSS 30080 KiB。
15 个输入中候选与高精度参考 14 个逐词相同、1 个相差 1 ULP：输入 c2a00001，
候选 05bfec5b，参考 05bfec5a。旧实现错误置零 7 个，候选错误置零 0 个。
这是固定样本诊断，没有添加容差；每项数值 passed/thresholds 与总体 numerical_acceptance
仍为 null。不能把整体 unittest 成功解释成 exp 正确舍入或完整 block 数值 PASS。

公开摘要：reports/execution/QWEN35_EXP_RANGE_CONTRACT_20261023/summary.json。
摘要保存 15 组原始词、相对源码 pin、外部依赖角色 hash 和日志 hash；不发布私有绝对路径。
历史 1618 个丢失值没有在本批重跑；本批也未运行官方 Torch、权重或任何完整模型。

本次使用 run_range_contract_bounded.py 和本地 attempt1.pins.json。Runner 固定
单 CPU affinity、512 MiB address space、20 秒 CPU 限额、25 秒 alarm；外层必须 timeout 30s。
Python audit 禁止网络、子进程和额外 ctypes 动态库；仅允许当前进程 None 与精确 R2 ELF。
这是 Python audit 层限制，不是任意原生库的安全沙箱保证。
32 个预先审核的文件包含静态递归候选 Python imports、R2 C++/ELF/receipt/compiler、
解释器及上述官方源/BlockFloat，执行前后比对。不是完整已安装 Python/NumPy 环境闭包。
日志由外层保存，JSON 单独记录结构门结果、pin 是否变化和数值 acceptance=null。

## 复现方式

使用仓库中的 runner 和 test，不修改生产文件；准备有 NumPy 的 Python 环境及已验证的 R2
ELF/build receipt。不要为本测试自动编译或下载。先核对公开 summary 的 source_pins 和
external_role_sha256；所用 Python、compiler、ELF 和 receipt 身份必须符合当前复现计划。
若环境不同，应记录新身份并作为新运行，不声称复现本次 exact native pin。

本地 JSON manifest 的字段为 native_library（ELF 实际路径）、interpreter_sha256、
pin_scope、files（仓库相对源码路径或外部绝对路径到 SHA256 的映射）。源列表取公开摘要
source_pins；将 external_role_sha256 对应到当地已审核文件。核验后才生成 manifest，
不能无条件把当前文件 hash 当作已接受身份。manifest 含当地路径，保持本地，不提交。

在仓库根目录执行以下命令，替换 Python、pins 和全新输出目录；shell 将 stdout/stderr
保存到本地日志。runner 不覆盖已存在的输出目录，外部 timeout 必须保留：

    timeout 30s <python> -B candidates/qwen35_35b_exp/run_range_contract_bounded.py --pins <local-pins.json> --out <new-local-output>

结构门须 4 项、0 skip、无 denied、pins 前后一致且 exit0。数值差异按原样保留，
即使与本批不同也不能临时放宽门；完整官方 block/硬件 replay 的验收仍是独立后续工作。
