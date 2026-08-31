# Local-agent handoff v7.2 — main only

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

## Latest q128 single-process result

The full harness contains Controller, Revision8B-B QK/PV, Block32 weights,
BF16 hi+residual and Block128 M/L/O. q128 PASS: 1,536 rows, 240 tasks,
3,222,082 cycles, Matrix/SFU stall 161/81, score/probability DDR bytes zero,
max error zero. The timeout was a testbench ready race; no production/generated
RTL changed. Evidence: `l5_q128_single_sim_attempt_result.json`.

## Unique next action

Extend the same RTL harness to q384, compare the frozen 180 reviewed rows and
require exactly 4,608 Block128 merge rows. Then q1024 reviewed rows/43,008 merges.

Then random backpressure, zero score/probability DDR and service curves.
Measure SiLU producer stall and select one lane only at <=2%; otherwise two.
L5.5 waits; floor315 token/s. CPU8-23, 24/30G, 600s/task.

Security: owner must review the ed06f4cf GitHub alert before dismissing; current audit says likely descriptive-prefix false positive.
