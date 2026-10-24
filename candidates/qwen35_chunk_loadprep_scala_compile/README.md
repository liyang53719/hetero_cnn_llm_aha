# LoadPrep 20 源 Scala compile-only 公开摘录

实际有限结论：PASS_ACTUAL_TWENTY_SOURCE_LOADPREP_SCALA_COMPILE_ONLY。

唯一编译 JVM 自然退出 0，20 份源共 122196 B 通过编译与类型检查。闭包为原 13 份 HardFloat、4 份共享源和 3 份 Chunk 源。TensorMath/ChainConfig 位于原 Protocol；原 EmitHeteroFP32Alu 的 App 定义仅编译，未作为入口执行。唯一入口是 scala.tools.nsc.Main。

342 项输入（314 工具、6 监督、20 源、2 源 manifest）前后内容及身份一致。116 个 class 共 950518 B，全部哈希、CAFEBABE 和库存经独立复核，23 个必要类型齐全；不是 116 个功能测试。闭合输出 128 文件、1479364 B，不随本包公开。

WNOWAIT 观测自然退出 code=1/status=0，随后已回收、进程组 absent、cleanup confirmed，未超时。保留 kill_attempted=true / signal_sent_before_reap：这是自然退出观测后的组清理，不隐去，也不写成超时强杀。

RESULT 内部计时 29.267010801 秒，launcher stdout 内部计时 29.268740754 秒；边界不同，不是独立外层 wall 测量。采样 descendants RSS 最大 335360000 B，children 累积 maxrss 328024 KiB；不能混称瞬时聚合峰值或独立阶段峰值。

本批不证明候选 Bundle/Module 构造、AddressPlan 行为、Chisel 展开、CHIRRTL、SystemVerilog/RTL 仿真、真实 ACK/背压、共享 Scalar FP32 数值、Host/root 发布、完整 chunk64/模型或利用率。原 Python 控制与本次编译资格分列，互不替代。五个 RTL 目标仍 0/5；旧 Qwen2 full 执行与清理 UNKNOWN 不变。

## 公开边界

恰好 8 文件：原字节 run_compile.py、launch_compile.py，相对 INPUT_PINS、说明性 REPRODUCE_COMMAND、SUMMARY、本说明、MANIFEST、ALLOWLIST。Scala 源属于独立源码包，本包只引用其 pins，不重复复制，也不据此声称已提交或公开发布。工具/JDK/JAR、监督支持、class、机器计划、日志、原收据、权限载荷、权重和数组均排除。

INPUT_PINS 的 342 项是相对逻辑名称和 digest，不是路径发现、下载或执行授权。87 个 classpath JAR 是工具集合子集，不重复计数，也不声称最小依赖。

原 launcher 要求 CPython 3.12.14 和 -I -S -B，以及未公开的 FROZEN_PLAN（182225 B，SHA-256 0a8d17bff69a26f6eaa1023d047a67397f25b161ef54824724f20de984652617）。本摘录不是完整可执行闭包，不能直接运行或伪造替代计划。REPRODUCE_COMMAND 仅解释编译器参数，不包含原 180 总 / 150 工作 / 5 清理 / 25 后核、单 CPU、RSS/AS、输出与身份清理保障，不能继承原实际资格。

原 Python 中 /proc、/proc/meminfo、/tmp 为通用 Linux 接口，按字节保留，不是私有机器位置。制作本摘录只做元数据、hash 和 AST 静查，没有再运行 runner、JVM、测试或编译，没有重哈希工具二进制。
