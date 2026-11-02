# Public21 Router / DownOwner 协议诊断（不作数值资格）

本目录只用于一次独立云端源码重建。原 159 个已审硬件 Scala 文件、官方 107 条 JAR 记录及原 Verilator 工具字节重新核验；不上传或导入本地 SV、classes、共享库、权重或 DUT 数据。workflow 不设置 artifact 上传。外层只输出固定有限阶段回执和白名单计数，完整子日志仅在该 job 本地 gzip 保留。

真实模块为 Public21QkvReductionRouter、DenseBlockReductionCoordinator、DenseTileSumBridge、TransposedDenseDownOwner 及 768 KiB 同步 banks。Matrix、vector、DDR 为明确协议 mock，零响应不是数值计算。目标为首个完整 N 窗口及第二 N 窗口第一 K partial 的终态；不宣称覆盖两个完整窗口、真实 4096 MAC、DMA 或实际 P0 resetRequired 根因。

流程：5 个有界工具准备阶段 → 159+6 Scala 源编译 → 官方原 Chiseltest 6.0.0 emit-only 路径 → LOW/SV/JNA 四个 switch 的 4710 typed 端口一致校验 → 独立 Verilator → 单线程 O0/no-PCH make → 官方 JNA context 加原协议驱动。原驱动 body 只有两处类型适配，可逆变换逐字节回原 Spec；初始化保留官方 reset=1、step(1)、reset=0，finally finish。JNA 库复制、coverage 输出均留在新 job 自有目录。

BUDGET_CONTRACT.json 明列 whole 7200 秒 / runner 6600 秒。准备共享 1800 秒含 cleanup，主阶段墙时合计 4320 秒，六次 cleanup 180 秒、摘要 60 秒，总计 6360 秒。逐阶段原时钟扣除剩余预约；最高 RSS 6 GiB 加非 DUT 1 GiB 动态门，AS 15 GiB、原文件/树/磁盘上界。其中 2,000,000,000 B 的 tree cap 仅约束每个 supervisor stage-run 目录；共享 W/emitted 的 LOW/SV/C++/库不受该 2 GB 门约束，而由真实 aggregate watch 12,081,306,272 B、每文件 512 MiB 及空闲 1.5 GB 门覆盖。不得声称共享输出已经逐阶段 2 GB 限制。它们是工程硬上限，不是完成或峰值预测。任何失败严格保留，不重试 nonce，不自动扩限。

本地证据：A 控制协议通过但未复现真实 P0 故障；B 首次 512 MiB Java heap 失败，第二次 JVM+backend 触 2 GiB，独立 Verilator 自身也触 2 GiB，均完整 cleanup，未到 B SIM_READY。本目录不是用优化或缩减硬件绕过这些故障，而是将同源码转换和 backend 分阶段搬到独立云端资源门。新的 emit-only 与直接 JNA API 已做本地小源码编译，尚不代表云端全链执行通过。

P0_PROTOCOL_INPUT.json 仅是原闭合 manifest 的 9 项 shape/address/命令数投影；来源 SHA 明确保留，不携带 tensor/weight 内容，也不把此小投影视作完整原输入重放。EXPECTED_PORTS.json 仅固定 typed 端口摘要。test_cloud_runner_flow 的工具/权威 helper 是明确 synthetic mock，只证明 runner 控制流和失败门，不能替代真实 CI 回执。
