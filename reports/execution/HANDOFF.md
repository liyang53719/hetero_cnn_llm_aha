# Local-agent handoff v7.0 — main only

## Git gate

```bash
git fetch --prune origin
git checkout main
git pull --ff-only origin main
./scripts/check_main_only_workflow.sh
./scripts/sandbox_validate.sh
```

Do not create a local/remote branch, PR branch or force-push.

## Accepted local boundary

```text
L5.1 Block128                         PASS, WNS +0.0000136495 ns
L5.2 Matrix Revision8B-B              PASS, H3 WNS +0.00490451 ns
L5.3 Controller                       PASS, WNS +0.00191498 ns
L5.3 Block32 weight                   PASS, WNS +0.0000125766 ns
L5.4 one/two-lane candidates          PASS, final selection OPEN
```

All timing margins are small. Power evidence is vectorless DC, not SAIF.

## Unique next action

Build a single q128 simulation containing Controller, Revision8B-B QK/PV, `fp32_block32_softmax_weights` and Block128 FP32 M/L/O. The previous trace bridge is useful but is not a single integrated E2 simulation.

Use `reports/execution/attention_e2_vector_pack_result.json`:

```text
q128:  1,536 full rows
q384:    180 reviewed rows
q1024:   108 reviewed rows
q1024 merges: 43,008
max sandbox dense-vs-blocked error: 1.0728836059570312e-06
```

After q128, run q384 and q1024 with random Matrix/SFU/output backpressure, zero score/probability DDR writes and measured service curves.

## Parallel SiLU gate

Review `reports/SILU_EDGE_POLICY_REVIEW_V7_0.md`. The standalone one/two-lane candidates pass ordinary finite vectors, but the special sweep found a Q4.12 zero-bin bias and a clamped-negative-gate times infinite-up class ambiguity. Freeze the policy before final selection. Measure offered/accepted pairs, producer stalls and queue high-water; choose one lane only when measured Matrix-producer stall is <=2%, then rerun the selected integrated path.

## L5.5

Execute the 11 cases in `reports/execution/e3_minimum_matrix.json` after L5.3/L5.4 close. Below 315 token/s pre-route projection, reopen the performance budget.

## Security note

GitHub flagged `sandbox_v69_result.json` in `ed06f4cf` as a GoCardless sandbox token. Inspection indicates the descriptive `sandbox_v69...` evidence string is the likely trigger; the current tree renames it. Confirm no actual token was copied before dismissing the alert as false positive.
