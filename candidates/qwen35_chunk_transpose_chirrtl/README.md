# Qwen3.5 Chunk 转置 owner：CHIRRTL 前端限定结果

本次双阶段自然结束：先仅编译独立 emitter，再真正构造一个 GdnChunkTransposeOwner 并产生一份 CHIRRTL 中间表示。501 份输入前后身份一致，原 146 个 class 与 3 个新 emitter class 均核验；两子 JVM 自然退出 0 后，原监督完成确权、回收、进程组消失与清理。完整执行约 9.67 秒。

实际前端检查覆盖 109 个端口叶，含 clock/reset；输入 57 叶 / 2030 bit，输出 52 叶 / 1904 bit。双阶段 receipt 和完整私有 decay/context 端口存在。独立解析 IR 的嵌套 bundle/flip，逐名宽方向与冻结源一致。tile 是一份 16×512 bit 的 reset 寄存器向量，即 1 KiB 载荷；上下文、计数器与控制寄存器另计。单模块没有子实例、外部模块或 memory 实例。

这些是构造与中间表示结构资格，不是实际功能验证。没有运行 firtool、SystemVerilog 或 RTL 仿真，没有证明真实 ACK、背压、阶段 3 checkpoint、阶段 4 失败恢复、held terminal 或共享 fabric 排空。没有构造 Scalar、Loan、Vector、MemoryEngine 等服务，也没有完整 chunk/Host/public/recurrent 接线或数值、时延、利用率资格。旧 Qwen2 执行/清理 UNKNOWN 不变。

## 公开增量与复现限制

七份原 emitter、Python runner/parser 及选定统一 diff 原字节保留。INPUT_DELTA.json 引用先前公开的 351 输入描述，只列 146 个已编译 class、3 个前次元数据摘要和 1 个 emitter 的相对标签/pins。没有重复生产 owner、模型或完整工具表，没有附 class、工具、IR、原始日志、原始收据、权限载荷或机器专属路径。

本包不是独立可运行闭包。原 launcher 仍严格要求同目录固定 SHA 的机器专属 FROZEN_PLAN.json，该文件故意不公开；相对标签不是路径替换模板。本包不提供自动下载、hydration、路径改写或绕过原门的运行方式。若要复现，需要重新闭合精确依赖与 fresh 输出计划，不能仅凭摘要改 pin。

原固定环境是 CPython 3.12.14 isolated/no-site/no-bytecode、JDK21、Scala 2.13.16、Chisel6.7.0。总窗 180 秒、共享工作窗 150 秒；编译最多 120 秒、展开最多 30 秒，均受共享绝对截止限制；清理 5 秒、后核 25 秒。单 CPU，地址空间 4 GiB，后代 RSS 采样上限 2 GiB，输出采样门 16 MiB。采样边界与累计 maxrss 不应写作瞬时全进程总峰值。

29 组纯 class-log parser 控制另行通过，只验证类日志接受/拒绝规则，不是 29 个硬件功能测试。前端采用固定 JDK21 子进程内 guard，预期弃用警告不表示失效；实际 exec、network、guard replacement 尝试均为零。未修改系统持久安全设置。
