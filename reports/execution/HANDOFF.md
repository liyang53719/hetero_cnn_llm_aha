# Local-agent handoff v7.5 — main only

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

q384 sampled E2 PASS with identical RTL: all frozen180 rows are contained in
2,304 compared rows, 756 payload tasks, 1,728 sampled merges, 14,756,016 cycles,
zero error/DDR score/probability traffic. Full controller E1 remains 1,872 tasks
and exactly 4,608 merges. Evidence: `l5_q384_sampled_e2_result.json`.

q1024 reviewed E2 PASS in two <=600s shards using identical RTL: all frozen108
rows are contained in1,440 compared rows, 1,062 payload tasks, 3,360 sampled
merges, zero error/DDR score/probability traffic. Full controller E1 remains
12,672 tasks/exactly43,008 merges. Evidence: `l5_q1024_reviewed_e2_result.json`.

L5.3 stress PASS:8 deterministic seeds,118,272 tasks per QK/SFU/PV flow,
354,816 total transactions; zero loss/duplicate/reorder/deadlock. Controller
curves are frozen; Block128 output backpressure PASS; score/probability DDR=0.
Evidence: `l5_attention_stress_service_result.json`.

## Unique next action

Measure real Matrix-producer stalls into fused SiLU. Select one lane only at
<=2%; otherwise two lanes. Rerun the selected integrated path, then L5.5.

Remote v7.2 adds 11-case adversarial Attention, service importer, integrated
quant source, 8-slot state/COW source and a 216-node Qwen3.8 trace. These are
E0/source-ready only. Keep Qwen3.5 `qwen3_5_moe` distinct from Qwen3.8
Flash-Next `qwen4_exp` (QSA/PLE/four-branch residual).

Then random backpressure, zero score/probability DDR and service curves.
Measure SiLU producer stall and select one lane only at <=2%; otherwise two.
L5.5 waits; floor315 token/s. CPU8-23, 24/30G, 600s/task.

Security: owner must review the ed06f4cf GitHub alert before dismissing; current audit says likely descriptive-prefix false positive.
