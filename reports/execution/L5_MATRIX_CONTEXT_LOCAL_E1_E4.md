# L5.2 Matrix context local checkpoint

Status: E1 PASS; full-top E4 incomplete; waiting for remote audit.

The production wrapper uses one physical 16x32 array (512 BF16 MAC lanes),
four accumulator contexts, and four generated HardFloat stages: preMul,
24x24+48, postMul, and round. Generated RTL is emitter output and was not
hand edited.

Real Verilator E1 passed:

- 1,000,000 dependent steps in an issue window of 1,000,000 cycles;
- four-context II=1 and 1,000,000 ppm issue utilization;
- 10,000 random-backpressure steps in 14,555 cycles;
- exact final accumulators, context/tag order, last, counters, flags, and
  protocol checks across all 512 lanes.

A one-lane probe using the exact production stage boundaries passed CLN22UL
1.0 ns with WNS `+0.000159681 ns`, zero unmapped cells, and no unresolved
references. This is diagnostic evidence only and is not the required full-top
E4.

The full 512-lane high-effort DC run was stopped by user request after 9,611
seconds in Mapping Optimization Phase 2 because its runtime was judged
abnormal. It produced no final timing, area, unmapped, or unresolved report.
The remaining `status.txt` predates this attempt and contains the old
pre-pipeline WNS `-1.35148 ns`; it must not be used for the pipelined design.

L5.2 therefore remains open. Remote audit should decide the bottom-up or
hierarchical DC strategy before another full-top run; frequency reduction,
false paths, multicycle exceptions, or a smaller array are not authorized.
