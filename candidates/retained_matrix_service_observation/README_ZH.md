# 原 Matrix service 阶段观测：TEMP / CPU120 FAIL

这是一份小型证据摘要，不包含新的诊断源码、运行依赖或原始日志，也不是可直接执行的复现包。此前 `e600e08012a5454bf2b728d7226250979085992b` 中的文本 parser FAIL 和静默 CPU120 FAIL 均保留；本次独立观测尝试仍为 **0/1 完整 case、CPU120 FAIL**，并未通过 service 数值验收。

## 新增的有限事实

独审核对 34 条连续阶段标记：本次可确认同次最终 prepared AST 门、factory 构造、Treadle 构造、`engine.ast` 身份及初始绑定检查完成；第一次 reset-high `step(2)` 返回，记录的 `completed_step_cycles` 为 2。未完成任何 fixture 数值 expect，也没有 driver group / wide-step 握手。

最后标记是 `first_clock.first_batch_done`；之后缺少 `first_clock.end`。其间可能包含标记尾部、reset-low poke、`step(3)`、计数更新和下一标记，**不能确定停止的精确位置，不能宣称 `step(3)` 已进入或完成**，也不能把记录的两步等同每个 endpoint 两次有效 gated edge。

采样 CPU 为 120.02 秒；外层墙钟约 140.780 秒。正常 native exit 未知，清理 reap 为 -9，外层返回 1，清理完成。阶段区间是全 JVM 线程/GC 与调度的括号采样，不是函数热点、稳定每周期成本、吞吐或 M128 预算证明。

## 不变的验收边界

没有完整 service 数值、seeded feedback、五个原始 Chisel block 的完整 M128 prefill、同一 4096 硬件全块回归、RTL 数值回放或 MAC 利用率结论。历史状态不因观测信息而升级。后继优化或新观察源码不在本摘要范围。
