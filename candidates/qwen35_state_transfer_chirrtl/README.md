# StateTransfer 单 owner CHIRRTL 前端公开摘录

本包提供可审阅源码、R1→R2 差分和有限实际结果摘要，不是完整执行闭包，也不是功能或模型通过证明。新的唯一 actual 完成 Chisel 前端展开并真正生成 CHIRRTL 硬件中间表示；有限状态为 PASS_OWNER_CHIRRTL_FRONTEND_ONLY，1 个 owner、64 个声明 IO 叶核对。

## 文件与范围

- source/GdnChunkStateTransferChirrtl.scala、run_chirrtl.py、launch_chirrtl.py、parser_controls.py 及两份 .patch 均保留原冻结精确字节，共 42,522 B。没有复制已存在的 owner/Chunk Scala 源。
- INPUT_PINS.json 是 381 个输入的相对逻辑名称与 bytes/SHA-256，共 297,560,375 B；只有其中 emitter 源实际收录，工具、51 个输入 class 和证据仅列 digest。87 个 JAR 是 314 工具的子集，不另计。
- REPRODUCE_COMMAND.txt 解释原入口与独立复现边界，不是新 runner、路径解析器或执行授权。
- SUMMARY.json 保留历史失败、设置错误、纯解析控制成功以及新 actual 的有限结论。原始日志、收据和复核全文均不公开。
- ALLOWLIST.json 限定恰好 12 个文件；MANIFEST.json 校验其余 11 个文件，自身不自哈希。发布时只取此清单，不能递归发布父目录。

## 历史不得抹除

R1 的编译和 Chisel 子 JVM 实际自然退出 0，已构造单 owner、检查 64 IO 并生成 CHIRRTL；但父进程后置 class-log 解析器错误要求隐藏 Lambda 名带数字，原整批仍为 FAIL。R1 未完成全部 381 项 AFTER 和最终 inventory，不能因子进程成功而改写总结果。

R2 只修正固定 JDK21 的类加载后置解析条件，并更新新计划路径/pin；owner、emitter 和工具字节未改。第一次 root 纯 parser 包装器先把 CPU soft/hard 设为 8/9 秒，而原控制入口要求 10/10 秒，形成包装器设置错误；之后在正确继承限制下，以不变源码完成 21 组纯解析正反例。该成功不是硬件执行，也不能删掉前次设置错误。

新 R2 唯一 actual 的通过另有独立实际复核，不继承 R1 或早期 compile-only 的 PASS。全 381 输入只在两个阶段之前与之后核验；阶段之间仅核验原 51 class 和新 emitter class，不能声称阶段间全 381 项都已核验。

## 结论上限

CHIRRTL 确实是生成的硬件中间表示，但本次没有 firtool lowering/宽度推断、SystemVerilog、RTL 仿真、真实 ready/valid 或 ACK 搬运、功能算术、FP32/GDN 数值、完整 chunk64 prefill、Host、完整 GDN 或模型验证。声明 IO 的宽度/方向检查不等于对内部算术宽度完成 firtool 推断。RTL 目标仍为 0/5，旧 Qwen2 full 的执行与清理状态仍为 UNKNOWN，未触碰旧流。

Java SecurityManager guard 已对固定 Java 闭包检查进程/网络调用与 guard 替换，不能当成任意 JNI 或网络隔离沙箱；类加载日志解析也不证明任意动态加载安全。采样资源上限不是连续瞬时峰值保证。

## 原 launcher 不能直接执行

launch_chirrtl.py 固定 CPython 3.12.14、隔离标志、原完整 FROZEN_PLAN.json 的 bytes/SHA 和监督输入。原计划被刻意排除，公开的相对 pins 不能替代它。不要伪造计划冒充原运行；换环境复现须另行审查并冻结配置，不继承本次通过。

源里的 /proc、/tmp 和纯控制中的虚构 /tmp 路径是通用 Linux 接口或测试夹具，命令说明中的 /opt、/tmp 是通用示例；原字节保留，不含本次 workspace/user/environment 专属根目录。

## 摘录制作边界

制作时只读小型冻结源码、计划、旧公开 pins 和独立闭合复核摘要。没有运行 tests、parser controls、emitter、JVM、编译器或静态候选检查器；没有重读或重新 hash 314 个工具、原 51 class、旧 owner/Chunk 源或原 actual 日志/收据；没有修改冻结候选、仓库，亦无 upload/push。

不包含原 FROZEN_PLAN、执行授权/ADMISSION、原 actual 收据或日志、私有复核全文、类文件、生成 IR、工具二进制、模型数组或权重。源码和状态摘录不是独立复现实际结果所需的完整证据包。
