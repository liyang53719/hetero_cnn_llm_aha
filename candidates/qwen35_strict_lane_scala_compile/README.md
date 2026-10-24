# Strict FP32 单 lane 编译限定摘录

一次离线 Scala 编译自然退出 0：10 份完整源、331 项输入前后相同，生成 55 个 class，29 个最低必需类均在。输出 class 的大小、SHA 与 magic 已独审核验，原身份/回收/进程组清理门闭合。

只有 scala.tools.nsc.Main 被调用；原 Emit App 仅作为整文件源码编译，没有调用 Module 构造或生成 CHIRRTL/SystemVerilog，更没有运行 HardFloat 数值或握手。先前软件参考通过不自动授予硬件资格。minnormal 边界 UF3 与旧 CPP1 的集成阻断仍保留。

本包只保留原两份监督源码与最小 diff，另提供有限摘要和相对 source pins。不重复发布新 lane/参考模型、工具、class、IR 或原始日志；生产源见此前单 lane 源码摘录。目标 CPython3.12.14 使用 -I -S -B。

原 launcher 仍严格要求未随本包发布的精确 FROZEN_PLAN，因此此摘录不是独立可运行闭包，不提供改 pin、改路径或跳过门的替代执行器。本公开包未重跑编译。详细范围与指纹见 SUMMARY.json / REPRODUCTION_PINS.json。
