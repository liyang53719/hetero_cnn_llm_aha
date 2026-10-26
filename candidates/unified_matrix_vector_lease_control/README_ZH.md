# Matrix / vector 独立租约控制：有限四 case DUT 证据

这是一份**后继控制器**源码和定点测试，不替换已冻结发射的 `UnifiedSharedResourceTop`，不新增或缩减其 4096 MAC / 16 FP32 vector / 1 scalar 物理资源，也不声明五块完整执行或高利用率达标。

新控制器在同一 accepted block context 下分别保有 Matrix、vector owner，采用事务、ownerSequence、stage、token、tile 和操作序数进行控制归属。生产者 fence 是私有接口，不可由 host 任意 Bool 冒充真实排空。此四 case 测试实际执行控制器 Chisel/Treadle，但 **Matrix/vector 物理响应、acceptedSteps 和 producerFence 均由测试台驱动**，没有实例化算术阵列、vector bank 或真实专家生产者。

实际四 case：同 DUT 两 profile 无 reset 且可同时持有两个 owner；三个终态同拍反例；held offer/accepted 序数及普通 poison 下合法排空；36 accepted offer 上限与未知 Matrix 返回隔离。日志四个成功行与最终 4/0 summary、owned JVM 清理和输入身份前后门必须同时成立。四份 retained low-FIR 相同只说明这四 case 的同控制电路，不是完整统一 top 的 RTL hash。

历史源 STOP 不改：R1 的 done/new step、short-error release/new vector offer、unknown raw return/release 同拍可误报 drained；R2 加终态/当前未知返回门；R3 用 issued+heldOffer 定义已接收序数，避免前一物理 offer 停顿时合法下一 serial 被误判。当前复制的是经过独立源审与实际 typecheck 的 R3 原字节，旧 STOP 不是硬件运行失败也不能被删除。

边界：没有实际 producer-origin 证明、DDR epoch 防重放、真实 memory feeder、全 block scheduler、向量数值、物理 Matrix completion、性能计数或 90% 利用率证明；未响应时依赖外部 watchdog/隔离，不保证有界错误完成。测试 reset 先撤销全部模拟流量，不是 DDR/物理流水安全 reset 证明。请求数据用于归属测试，不能原样作为合法 BF16 算术刺激。最终父端必须以所有 client reservation 覆盖 begin 到 owner grant 前的窗口，再允许 block end；该真实父连接属于后继候选。

## 来源与复现

本包仅两个新 Scala 原件；协议和 bank 引用已发布 A 包固定 commit。四源曾共同编译，但 bank 类未被本 DUT 实例化。按 `REPRODUCTION.json` 先重构已资格 557 baseline，再编译 preserved-ABI 九源得到 68 类；验证无重名后组成 625。四源 fresh compile 产生 17 类，实际 test stage 为 642。使用固定 106 JAR / Scala 2.13.16 / Chisel 6.7.0 / ChiselTest 6.0.0，不用任意历史 class fallback。外部 HardFloat 源仍是继承的 pin 依赖；没有上传 class、low-FIR、权重、工具或大中间结果。

compile-only 与 test-only 是两个独立授权门。编译预算为 120 CPU / 150 work / 160 cleanup / 180 total / 210 outer；测试为 60 CPU / 90 work / 100 cleanup / 120 total / 150 outer；单核、heap 1 GiB、AS 4 GiB、sampled RSS 2 GiB。实际 sampled CPU 59.07 秒接近 60 秒，不保证其他环境或扩大测试能 fit。复现说明本身不授予执行权限，也不自动串联测试、SV 或 Yosys。
