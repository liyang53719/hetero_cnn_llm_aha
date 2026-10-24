# Qwen3.5 Chunk 转置 owner：仅 Scala 编译资格增量

本包记录一次已结束的离线编译：27 份完整 Scala 源、351 份输入前后身份一致，产生 146 个 class，45 个必需类子集全部存在。编译子进程自然退出 0，原监督记录确权、回收、进程组消失及清理完成。完整运行约 34.33 秒。

资格只到 Scala 编译。没有运行候选 App、构造 Module、展开 CHIRRTL、生成或仿真 RTL，也没有验证真实内存 ACK、阶段 checkpoint、背压、held terminal、数值计算或整块接线。先前纯 Python 合同模型结果没有被用作本次编译通过的替代。

## 最小增量与复现边界

两份 Python runner 和两份统一 diff 均为本次冻结原字节。相对上一 Derived R2 编译，仅增加已独立发布的 GdnChunkTransposeOwner.scala 及其源 manifest，保留原 349 输入、26 源顺序、314 工具、87 JAR、6 监督源。REPRODUCTION_PINS.json 引用上一相对输入说明的精确哈希，只列新增 2 项；不重复生产源码、模型或完整工具表。

公开包不是可独立执行的完整闭包。原 launcher 精确要求同目录被固定内容哈希绑定的 FROZEN_PLAN.json；该机器专属计划故意不在公开包中。缺失计划不能通过路径模板、改 pin 或跳过原门来替代。本包没有自动 hydration、下载或执行入口。源码复核可对照相对 pins；重新执行必须重新闭合实际依赖与 fresh 输出的固定计划。

原固定环境为 CPython 3.12.14 的 isolated/no-site/no-bytecode 模式、JDK 21、Scala 2.13.16 与 Chisel compiler plugin 6.7.0。唯一 JVM main 为 scala.tools.nsc.Main；Emit/App 源只是编译输入。

原预算为 180 秒总窗、150 秒共享工作窗、5 秒清理、25 秒后核，单 CPU、4 GiB 地址空间、2 GiB 采样后代 RSS，16 MiB 采样输出门。采样门不是瞬时总资源证明；本次实际成功不承诺未来完成时长。

不包含机器路径、原始日志或收据、权限载荷、工具/JAR/class/IR 文件。摘要中的收据只保留大小及 SHA-256。旧 Qwen2 执行与清理 UNKNOWN 不因本批编译改变。
