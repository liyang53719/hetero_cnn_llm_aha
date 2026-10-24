# 两源 Chunk Scala compile-only 公开摘录

实际独立复核：PASS_ACTUAL_TWO_SOURCE_QWEN35_CHUNK_SCALA_COMPILE_ONLY。本包只是源码与状态摘录，不是完整可执行闭包。

## 本包包含什么

- launch_compile.py 与 run_compile.py 保留冻结 runner 的精确原字节，未替换路径或修改行为。
- INPUT_PINS.json 只列相对逻辑名称及 bytes/SHA-256：2 个 Scala 源共 12690 B、314 个工具共 296950644 B、6 个监督辅助输入和 1 个合同包 manifest，共 323 项、297204940 B。87 个 classpath JAR 是工具集合的子集，不重复计数，也不声称是最小依赖集合。
- 两份 Scala 已在 db4977f 的 candidates/qwen35_chunk_contract/source/ 中提交，本包只引用，不复制。原编译顺序为 GdnChunkProtocol.scala、GdnChunkAddressPlan.scala。
- REPRODUCE_COMMAND.txt 是显式变量形式的编译器入口模板，不自动寻找依赖、改写路径或下载文件，也不是新的通用 runner。
- SUMMARY.json 记录有限结论与独立复核摘要 pin。ALLOWLIST.json 限定恰好 8 个公开文件；MANIFEST.json 校验其余 7 个文件，自身不自哈希。不得递归发布父目录。

## 已复核的有限实际结果

唯一实际尝试自然退出 0，得到 27 个 class 文件，共 124993 B；8 项预期类型/object/内部 Plan 类均存在，323 个冻结输入的 before/after 一致。launcher stdout 内部单调计时约 9.967406827 秒，此处保留 9 位小数，不是独立测量的外层 wall time。

子进程 WNOWAIT 观测 code=1/status=0，随后已回收、进程组 absent、cleanup confirmed，未超时。kill_attempted=true、kill_result=signal_sent_before_reap 是观测自然退出后的原进程组清理，不是超时强杀，也不能删除此事实美化结果。

独立实际复核：12784 B，SHA-256 8a919685a8f65e03eebd5293d383a8c2d35a0356ae6c53548774d0af6935e579。原文未公开，摘要 pin 不代表全部原始证据已公开。

本次只证明 Scala 编译通过，不是 AddressPlan 求值、候选构造器或 Module 执行、Chisel 构造/展开、RTL、真实 ACK/握手、数值、chunk64 prefill、完整 block 或利用率验证。五个 RTL 目标仍为 0/5；旧 Qwen2 full 的执行与清理状态仍为 UNKNOWN，不继承任何旧 PASS。

## 不能直接执行原 launcher

原 launcher 固定 CPython 3.12.14、隔离标志及未收录的机器 FROZEN_PLAN.json（162609 B，SHA-256 8c7c138b20834b6664e40b261d1e3113b3d5386f3afda1c262c41b2fd3cb3de9），还依赖外部监督与工具文件。本包明确排除原计划、机器特定路径和运行授权，因此两份 runner 源仅供审阅，不能直接运行。不要伪造替代计划冒充原冻结运行。

相对 pins 用于接收方独立取得、映射和校验输入；它们不是路径解析器或执行授权。入口模板不具备原 180 秒全局期限、150 秒工作期限、CPU/RSS/输出上限、身份确认、WNOWAIT/回收/清理保障；独立运行须另行审查并冻结这些配置，不能宣称与本次原运行等价。

原 Python 源中的 /proc、/proc/meminfo 和 /tmp 是通用 Linux 接口常量，按原字节保留，不是机器私有路径。

## 摘录制作边界

制作时只读 runner 小型源码/元数据及旧脱敏 pins，复用被 DELTA 声明不变的工具/支持 pins；未读原机器计划、实际日志/收据、Scala 源或工具二进制。仅做 AST/内存代码对象语法及元数据/字节哈希一致性检查，没有 import/exec 候选、运行静态检查器、测试、编译器或 runner，也没有修改仓库或 push。

不包含原 FROZEN_PLAN、日志/收据/ADMISSION、数组/权重、JDK/JAR 或其他工具二进制、class 或任何实际运行产物。
