# 实际发射证据：PASS 范围仅结构与身份；完整任务 INCOMPLETE

DONE：原四级 FMA 库实际发射；最新原 Host high 捕获，再从同一已接受 high/annotations 完成 lower 与 SV 发射。它是 **Chisel 数值仿真后端**，不是模型通过后冻结的最终 RTL。保留 4096 Matrix MAC 与 32-bank Vector 定义；不把 bank 数当作已验证的每周期 issue/retire 能力。

实际 Host 有 12 项产物，SV 194990051 字节；独立核对 8964 个 DontTouch、85 端口、92 模块、18 存储表示和 17 外部绑定。两个工具源编译得到 24 新类，1033 baseline 类不变；lower 不重新 elaboration。完整数值和最终 RTL 回放仍五块 M128 **0/5**，没有周期/利用率实测，也没有 80% 或 90% 达成结论。

ONGOING：物理 source closure 仅静态准备，13 provider、iDMA 294 编译项、52 include-tree 文件、367 pins。四个 DPI 测试平台属于递归 inventory，但不在实际编译及 literal include 可达闭包。此词法核对不是预处理、elaboration 或链接 PASS。两个同名 HardFloat module 字节相同且没有相关宏依赖，另保留经审计六模块 FMA 子集；本包只给 hash，不上传生成 SV。

历史不可抹除：首次 FMA 6 GiB 门限在 JVM 启动前失败，复核后仅 FMA 改为 5 GiB 门限，Host 仍 6 GiB。lower R1/R2 草稿未执行；scope 文案与 Input/Output 大小写契约修复后仅 R3 实际运行。旧编译缺 helper 的失败见父包。历史 pin 均保留，不用新 PASS 覆盖旧失败。FMA stall 下 flags 时序未证明，独立 carrier 端口不是流水数值回放。

复现仍 requires-parent：原精确 high/annotations、31 硬件源（父闭包仍有缺源）、baseline 类、精确工具依赖及真实 provider 均需恢复并重验。本包 helper 源字节精确；emitter 两处本地路径替换为占位符，仅未编译模板，不称行为等价。SOURCE_PINS 记录原/公开双 hash；不能直接把模板当实际已编译源。公开检查只校验元数据和身份，不运行编译器或数值模型。

TODO：先冻结整个 frontend 子进程树预算，审查跨层时钟和真实物理 provider，再执行物理前端、生成 VHost header 和完整 driver 编译/协议资格；目前前端、link、DUT 全部 NOT RUN。--hierarchical 即使不带 --build 也可生成子进程，不能按单进程预算。磁盘门限不足不得开跑，更不得缩硬件。随后继续五块并行 M128 数值闭环；通过才冻结同刺激最终 RTL。MoE tie 契约仍待用户明确，1024/1224 不阻塞 M128。
