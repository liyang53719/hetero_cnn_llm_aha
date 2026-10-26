# Runtime GDN LoadPrep：固定 max32 phase1 控制叶（有限 PASS）

新 `GdnRuntimeChunkLoadPrepOwner` 无构造时 profile 参数，固定 5-bit head/6-bit runtime head-count 接口，接受 keyHeads=16、valueHeads=16/32。仅控制与地址运算，无新增 scalar/Vector/Matrix/SRAM/MAC；复用已公开的新版 GdnChunkProtocol（不能换回旧 4-bit）。原不可变 AddressPlan 和旧 owner 不改。

本次真正 ScalaTest/Treadle 4/4 通过。主要测试一份 DUT、初始一次 reset，runtime 16→32→16，选 head15→31→15，各做 M128 chunk0/1，共 **6 个单 head/chunk phase1**；不是执行全部16/32 heads 或完整 block。每成功 phase 检查64 Add 请求/响应、1536 QKV+64 gate 写、1600写ACK/102400 bytes；scalar 为确定性测试替身，不是 HardFloat 算术。另测 M16 padding、14个 pre-I/O 拒绝、最后写ACK错误（102336 bytes，不给完成）和 held done。计数证据是实际4/4日志+执行测试断言，无独立 raw transaction trace。

布局 ID0/version1 为 value-head-expanded FP32 prepared Q/K/V/gates；producer 从 compact Q/K 按 value_head/(valueHeads/16) 取源并展开，consumer 直接用 value_head，不能二次除2。chunk0 需 phase0 state receipt；chunk1 需同 head/tag/generation 的前chunk phase16/17 ACK。receipt 是私有叶合同，不认证调用方真的执行了 producer，完整 trusted producer/调度 fabric 尚未接通。

传输 tag32||sequence32 依赖单 outstanding、exclusive/no-stale 服务，不是 transaction epoch/replay 防护；父 fabric 需映射不复用身份。错误后锁定，partial writes 不回滚，reset 需外部服务排空或共同 reset。未完成 chunk coordinator/persistent-root fence。

原 fresh compile28源，106JAR；140新class仅作者hash及独审当前size索引，无动态class origin追踪。140 launch pins 前后是 source-bound 聚合，不是逐项保存 PASS，更不是完整JDK/Python/native闭包。原环境继承 os.environ，JAVA_TOOL_OPTIONS/_JAVA_OPTIONS/JDK_JAVA_OPTIONS 和 Python flags 未留历史快照；不能由日志无注入文字推空环境，assert launcher 也不能通用化到 -O。保留作者/root确认非优化命令与证据层级，不事后补写。

实际 wall100.15538698690943s、采样 group CPU99.83s/RSS376115200B；CPU硬限逐进程，heap512MiB非RSS硬限，未保存最大采样间隔或最终wait4 CPU。cleanup锚定原组和已观测身份，保留leader两次空扫描再回收，不排除未观测逃逸；zombie清理SIGKILL不是资源FAIL。

独立纯整数公式每模式1033 checks/403200地址枚举仅公式控制，不扩大实际head覆盖。本批未产生或宣称统一五profile完整top同RTLhash、4096算术、模型/DDR/PPA/MAC/频率通过。旧FAIL及canonical任务状态原样，后继phase2/3/4未纳入。

复现源与 exact role argv 见 SOURCE_PINS.json / REPRODUCTION.json；需另外合法恢复依赖并取得有界运行准入。本包不提供 runtime/JAR/classes/IR/权重/输入，包装阶段不运行 Scala/JVM/native。
