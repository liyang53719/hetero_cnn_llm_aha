# Local-agent handoff v7.0 — main only

## Git gate

Fetch/pull main, run `check_main_only_workflow.sh` and sandbox before work. Before push fetch/rebase/rerun. No branch, PR branch or force-push.

## Accepted local boundary

```text
L5.2 Matrix H3                  PASS, WNS +0.00490451 ns
L5.3 Controller                PASS, WNS +0.00191498 ns
L5.3 Block32 weight            PASS, WNS +0.0000125766 ns
L5.3 Probability hi+residual   PASS, WNS +0.000114202 ns, max error 0.00064075
L5.4 one/two candidates        PASS, final selection OPEN
```

All margins are small. Power is vectorless DC, not SAIF.

## Unique next action

Build a single q128 simulation containing Controller, Revision8B-B QK/PV,
Block32 weights, BF16_hi+residual 64-step PV and Block128 FP32 M/L/O. Trace
bridge/vector packs are not single integrated E2. Use the frozen v7.0 pack:
q128 1,536 rows; q384 180 rows; q1024 108 rows/43,008 merges.

Then random backpressure, zero score/probability DDR and service curves.
Measure SiLU producer stall and select one lane only at <=2%; otherwise two.
L5.5 waits; floor315 token/s. CPU8-23, 24/30G, 600s/task.

Security: owner must review the ed06f4cf GitHub alert before dismissing; current audit says likely descriptive-prefix false positive.
