# 四源 StateTransfer Scala compile-only 公开摘录

实际独立复核：PASS_ACTUAL_FOUR_SOURCE_STATE_TRANSFER_SCALA_COMPILE_ONLY。本包只是源码与状态摘录，不是完整可执行闭包，也不是候选 RTL 或搬运功能通过证明。

## 本包包含什么

- launch_compile.py 与 run_compile.py 保留冻结 runner 的精确原字节，未替换路径或修改行为。
- INPUT_PINS.json 只列相对逻辑名称及 bytes/SHA-256：4 个 Scala 源共 25449 B、314 个工具共 296950644 B、6 个监督辅助输入和 2 个 source manifests，共 326 项、297219204 B。87 个 classpath JAR 是工具集合的子集，不重复计数，也不声称是最小依赖集合。
- 原编译顺序为 Protocol.scala、GdnChunkProtocol.scala、GdnChunkAddressPlan.scala、GdnChunkStateTransferOwner.scala。四份源码及两份 source manifests 均只引用 digest，不复制、不声称由本包发布。
- REPRODUCE_COMMAND.txt 是显式根目录变量形式的原编译器参数入口模板，不自动寻找依赖、改写路径或下载文件，也不是新的通用 runner 或 relocation resolver。
- SUMMARY.json 记录有限结论与独立复核摘要 pin。ALLOWLIST.json 限定恰好 8 个公开文件；MANIFEST.json 校验其余 7 个文件，自身不自哈希。不得递归发布父目录。

## 已复核的有限实际结果

唯一实际尝试自然退出 0，得到 51 个 class 文件，共 277143 B；全部 class 的 SHA-256 和 CAFEBABE 已复核，15 项预期类型均存在。326 个冻结输入的 before/after 完全一致且匹配原 plan pins。闭合输出共 63 个文件、746367 B，本包不包含这些输出。

RESULT 内部单调计时约 16.587893995 秒，launcher stdout 内部单调计时约 16.588148327 秒，均保留 9 位小数；不是独立测量的外层 wall time。采样资源观察和累积 children maxrss 的有限解释见 SUMMARY，不能当作瞬时峰值或独立阶段 maxrss。

子进程 WNOWAIT 观测 code=1/status=0，随后已回收、进程组 absent、cleanup confirmed，未超时。kill_attempted=true、kill_result=signal_sent_before_reap 是观测自然退出后的原进程组清理，不是超时强杀，也不能删除此事实美化结果。

独立实际复核：18348 B，SHA-256 3cd8d101cad9cc2c7be5e40f42203fa6f12f95246c91d7d3db46d32dcf0d1f09。原文未公开；此摘要 pin 和私有证据 pins 不代表全部原始证据已公开。

本次只证明四源 Scala 编译及类型检查通过，不是候选 Bundle/Module/Plan 构造或执行、Chisel 展开、RTL、真实 ready/valid 或 ACK/搬运数据、response nbytes 检查、receipt producer 真实性、全局 root lock、FP32/GDN 算术、chunk64 prefill、完整 block 或利用率验证，也不是 Host/public/recurrent/root 发布资格。五个 RTL 目标仍为 0/5；旧 Qwen2 full 的执行与清理状态仍为 UNKNOWN，不继承任何旧 PASS。

## 不能直接执行原 launcher

原 launcher 固定 CPython 3.12.14、隔离标志及未收录的机器 FROZEN_PLAN.json（165616 B，SHA-256 4ee795a6ce78d05790cb0a431ae73d45cb9e6c1ab36cf147ff41327d3ac264f6），还依赖外部监督与工具文件。本包明确排除原计划、机器特定路径和运行授权，因此两份 runner 源仅供审阅，不能直接运行。不要伪造替代计划冒充原冻结运行。

相对 pins 用于接收方独立取得、映射和校验输入；它们不是路径解析器或执行授权。入口模板不具备原 180 秒全局期限、150 秒工作期限、CPU/RSS/输出上限、身份确认、WNOWAIT/回收/清理保障；独立运行须另行审查并冻结这些配置，不能宣称与本次原运行等价。

原 Python 源中的 /proc、/proc/meminfo 和 /tmp 是通用 Linux 接口常量，按原字节保留，不是机器私有路径。原环境 PATH 为通用 /usr/bin:/bin；不公开机器专属 workspace 或 home 绝对路径。

## 摘录制作边界

制作时只读小型冻结 plan、runner 源码/元数据、旧脱敏 pins 和小型独立实际复核摘要；工具/支持 pins 从旧脱敏包复用并与本次 plan 元数据逐项核对。未读四份 Scala 源码、原实际日志/收据、工具二进制或旧 Qwen2 full 活动流。仅做 AST/内存代码对象语法及元数据/字节哈希一致性检查，没有 import/exec 候选、运行静态检查器、测试、编译器或 runner，也没有修改仓库、执行新 actual 或 push。

不包含原 FROZEN_PLAN、日志/收据/私有复核/ADMISSION/执行授权、Scala 源、数组/权重、JDK/JAR 或其他工具二进制、class 或任何实际运行产物。
