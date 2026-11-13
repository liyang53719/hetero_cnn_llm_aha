# Current work breakdown on consolidated main

## Closed and accepted

- L0-L3 control/upstream/wrapper/shared-fabric baselines.
- L5.1 Block128 component E1/E4, with effectively zero timing margin.
- L5.2 Revision8B-B 512-lane, five-stage/five-context Matrix E1/H3.
- L5.3 Controller and Block32-weight component E1/E4; the trace bridge is accepted only as non-single-simulation evidence.
- L5.4 one- and two-lane fused-SiLU standalone E1/E4 candidates.

## Current local-agent critical path

1. Build one integrated q128 QK -> Block32/Block128 M/L/O -> PV simulation using the deterministic vector pack.
2. Extend to q384 and reviewed q1024 rows, exactly 43,008 merges and random backpressure.
3. Freeze SiLU edge behavior, measure Matrix-producer stall and select one/two lanes.
4. Execute the 11-case integrated E3 matrix.
5. Run 28-layer q1024 >=300 token/s within SRAM and DDR limits.

## Sandbox v7.0 completed

- Attention pack: 1,536/180/108 q128/q384/q1024 rows, max error `1.0728836059570312e-06`.
- SiLU: 625 special vectors and 160 stall scenarios; two edge policies require review.
- Quant: 8,192 arbitrary K-tail schedules plus source-ready sequencer RTL.
- State: 5,000 adversarial transactions, generation wrap and zero page leak.
- E3: 11 coverage-driven cases and mandatory counter contract.

## Other local dependencies

CNN/AHA E1/E4; pinned llama.cpp parity and quant RTL/PPA; production state RTL/iDMA E3; official Qwen3.5/Qwen3.8 backends; real llama.cpp/GGUF; SRAM/post-route/PVT/SAIF and final Archspec promotion.

## 2026-11-13 当前云端 hetero 主线（中文状态，覆盖上文历史资格的适用范围）

上文历史组件/控制/局部接受不等于当前五块M128完整数值通过。当前仅hetero，固定4096 Matrix MAC、同一硬件定义/接口/资源与统一RTL身份；五块完整原Chisel为0/5，完整RTL与有效MAC利用率未测。

- done（范围限定）：新完整Host+17native+AXI checkpoint局部恢复；旧冻结Qwen2首RMS40/128行实际写回245760字节与独立参考相等。不是完整首RMS或block。
- done（结构限定）：独立ascending一致修复候选的Scala/Chisel emit/HWIR lower成功，全部接口/extern及105assert声明、17native保持；4项静态/边界测试通过。不代表数值或RTL通过。
- ongoing/TEMP：该候选仅改变Attention Commands/lease/router三处顺序绑定，norm C1/C2及RoPE B1保持。新源码/IR身份不得装载旧checkpoint或迁移旧通过；当前执行镜像未替换。
- ongoing/INCOMPLETE：L3双契约独立参考已到postnorm与完整FFN gate/up；旧ascending与安装pair序的数值差异保留。尚缺SiLU/down/final残差及原Chisel完整执行。
- blocked：原29364拥有线程poll为Unknown、无终态，未重复恢复。需确切终态或用户明确允许旧状态未知下独立恢复；下一管理器共享锁/原子发布已通过假负载测试，不能反证旧无锁任务已停。
- blocked：L0原underflow FAIL保留；35B两块真实权重缺失；MoE同分契约未擅定。
- todo：在新候选身份上完成五块M128原Chisel完整数值链，再冻结源码/输入/参考/配置，生成同一份RTL并同刺激回放。32lane共享Vector方案不减少4096 Matrix，仍须新统一硬件全重测。长档1024/1224待明确，不阻塞128。

本轮证据及精确局限见 [19:33摘要](round_20261113T1933/SUMMARY_CN.md)。源码/数据/原始日志仅本地，远端仅保存允许摘要与计划；未发布候选实现。
