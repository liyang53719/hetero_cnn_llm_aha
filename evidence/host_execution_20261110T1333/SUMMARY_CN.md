# 13:33 原 Host 执行链推进：TEMP / INCOMPLETE

本轮有本地编码和实际测试，不是仅检查。被审查拒绝的完整候选源码/原始日志没有换渠道上传；本提交仅摘要与哈希，源代码及唯一失败证据仍本地保留。

## done：PASS 仅下列范围
- native Scala/JNA 生命周期：64个Matrix实例含未eval/部分eval、正常finish与资格异常、重复abort；ICG/iDMA各32实例清理。此前未初始化protectlib句柄的final崩溃已最小修复；不保证任意首次eval内部native故障恢复。
- iDMA跨wrapper字段贯通：仅无状态wrapper，唯一无条件等宽UInt alias；官方类型/声明检查通过，真实Adapter闭包重写159处，保留真实r_ready到r_last组合依赖。目标metadata完整保留，977条DedupedResult、4609条DontTouch目标策略回归通过；不使用AllowCycles或clock补丁。
- 两次实际保护失败分别发现历史dedup metadata判定过严、连接提前引用父模块晚声明值；均保留并修复，没有跳过官方检查。无关模块不改。
- 纯宿主运行库性能修复：结构hash缓存保留equals；ExpressionCompiler改顺序iterator；Scheduler构造删除保持重复计数/对象身份/顺序；Scheduler执行保持每次.toSeq快照、异常顺序。对应2000输出×5输入、reset/寄存步进与依赖图/assigner顺序对照通过，另含10000多重集边界。均非硬件吞吐或数值通过。
- 当前完整pin schema核对122端口/41输入相同，真实AXI driver编译/配置映射与协议小测完成，独立参考不进入DUT内存。

## 实际原 Host 证据
固定4096 MAC的同一原始lowered IR SHA仍为aaa2dcb5eebdc2fefb990ca45ab5ee493686983e4654d4d3d63c17dd6775ab3a，顶层接口未变。会话89081在365.09s完成engine构造及17真实native绑定，已越过原iDMA伪环；但600s预算时仍在reset执行，未发射prefill。

会话90369、98036、89081各在原600s预算终止，均未声称完成。新会话36793启用经对照的快照iterator、6GiB JVM及单CPU，以避免已测4GiB堆full GC压力；这不是增改NPU资源。其600s预算内仅在完整构造、绑定、schema/reset门通过后，才尝试原完整21-op Qwen2 M128真实AXI事务。此提交时终态未取得；没有重复并行Host。

## 全局边界与下一步
五块M128完整数值仍0/5；无最终同RTL回放PASS、无完整block有效MAC利用率实测。原L0 fatal underflow保留；35B两层原CDN访问阻塞未绕行。L3真实输入桥并行完成：22 commands/261 descriptors、13个BF16真实readonly tensor和原trig全部核hash，原Config+mmap loader通过15 readonly allocations/20 DDR observations，virtual score/prob未预装；此仅格式映射资格。不能把数学参考/格式/生命周期/构造资格算数值PASS。
继续原身份取得36793终态及实际事务证据，若产生完整DUT输出，再与冻结独立参考比较。保持原FP32/BF16契约、MoE基线及固定硬件。未清理仓库数据，运行/唯一证据全保留。必要候选代码的远端发布仍待审查放行，不把摘要提交冒充源码已同步。
