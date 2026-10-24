# LoadPrep 单 owner CHIRRTL 前端限定摘录

实际独审结论：PASS_SINGLE_LOADPREP_OWNER_CHIRRTL_FRONTEND_ONLY。

两个顺序 JVM 分别只编译新 emitter、只构造一次 GdnChunkLoadPrepOwner。均观测自然退出0，WNOWAIT code1/status0，随后回收、进程组 absent、cleanup confirmed。原记录的 kill_attempted=true / signal_sent_before_reap 是自然退出观测后的组清理，不隐去或写成超时强杀。

462 项输入前后内容与身份一致。原116个 class未重编；新 emitter恰3个 class、25806 B。实际类日志4737条，普通候选22个（19输入+3新emitter）、hidden385个/14精确宿主；没有 hardfloat、gemmini、BlockScalarFloat或F32加载。编译存在不等于允许加载或实例化。GdnScalarClient/ScalarRequest仅为外借Scalar服务的接口Bundle，ScalarOp只提供常量，不生成算术服务。

唯一 CHIRRTL为 GdnChunkLoadPrepOwner.fir，131416 B，SHA-256 b95431cf614e93810812bb1c313c1ff3dee456eb8ff715956f8dd947900b139f。独立解析真实端口树得到97叶、67输入/30输出，2193输入位/1197输出位；含一个Clock和96个UInt。只有一个同名circuit/module，无子实例、extmodule、intmodule或mem/cmem/smem/mport。原IR不随本包公开。

固定JDK21 emitter guard完成安装并保持，exec/network/replacement尝试均0；它不是任意JNI通用沙箱。原5条编译弃用警告及JDK SecurityManager移除警告保留在私有日志，不能假称没有警告。

RESULT内部计时9.002016603秒，launcher stdout内部计时9.002297696秒，编译阶段5.551541秒、展开阶段2.839975秒。不是独立外层wall测量。采样聚合RSS231337984 B、children累积maxrss226584 KiB，不代表瞬时峰值或各阶段独立峰值。

这次确实生成CHIRRTL硬件中间表示，但仅证明该单owner的前端构造、声明叶宽/方向和连接构建。没有完整FIRRTL/firtool降低与推断、SV/RTL仿真、真实内存ACK/背压、Scalar握手或FP32数值验证；也没有Host/root发布、完整chunk64、模型或QoR资格。五RTL目标仍0/5，旧Qwen2执行与清理UNKNOWN不变。此前Python、编译及其他owner资格不能替代本次或扩展本次。

## 公开边界与复现限制

ALLOWLIST恰12文件。7份原源/patch逐字保留，含新emitter、两个runner、纯parser控制和三个差分。没有重复发布LoadPrep生产owner或116个class，没有工具/JDK/JAR、机器FROZEN_PLAN、日志、原收据、权限载荷、数组或权重。

INPUT_DELTA引用独立compile摘要的342 relative pins，并列本批120项增量（116旧class、3终态metadata、1emitter），合计462；只含逻辑名、bytes与SHA。基础pins及所有实际依赖必须另外取得和核对，不自动下载、发现路径或授予执行权。

原launcher要求CPython3.12.14与-I -S -B，并固定未公开机器FROZEN_PLAN（265723 B，SHA-256 5a8114c85c37d1ddca057b3b49e434a182151077995e864d3174268520b1a8c0）。本摘录不是独立可执行闭包，不要伪造替代计划直接运行。原总180秒/共享150work，compile≤120和elaborate≤30均受共享窗限制，cleanup5/post25；单CPU、heap1GiB、AS4GiB、采样组RSS2GiB、owned16MiB门未扩大。

纯parser程序固定的小合成路径仅用于字符串比较，不是机器证据路径；它运行27组解析控制，不是CHIRRTL测试。静态审阅可仅hash与AST/内存compile，不运行launcher、候选或旧测试。本摘录制作未重复任何actual或工具大hash。
