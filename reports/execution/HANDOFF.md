# Local-agent handoff v7.10 — main only

## Git gate

```bash
git fetch --prune origin
git checkout main
git pull --ff-only origin main
./scripts/check_main_only_workflow.sh
./scripts/sandbox_validate.sh
```

No branch, PR branch or force-push.

## Accepted closure

```text
L5.3 Attention numerical E2          PASS q128/q384/q1024
L5.3 random-backpressure service     PASS, 354,816 transactions
L5.3 score/probability DDR           0 / 0 bytes
L5.4 fused SiLU                      PASS, one lane selected
L5.4 producer stall                  0%, queue high-water 7
```

The 4-lane tile / 4-row merge SFU components pass E1/DC, but the stress projection is 314.448 t/s and therefore fails the 315-t/s review gate. Retain the component evidence; do not enter E3 with it.

## Unique next action

Implement balanced 8x8 Attention SFU:

```text
8 elastic tile math lanes
8 parallel M/L/O merge rows
same 16x32 tile store
same FP32 operation order
scores and probabilities remain on chip
```

Sandbox preflight: nominal 323.764 t/s, stress 322.944 t/s, conservative area upper bound 684,314 library units. Use `reports/execution/l5_5_balanced_8x8_sfu_e0_result.json`. A source-ready `rtl/attention/fp32_mlo_merge8_candidate.sv` is provided.

Local hard gates: numerical mismatch zero, deterministic random backpressure, WNS>=0, unmapped/unresolved=0, stress>=315. Preferred engineering gate is stress>=320. Then run real Matrix/SFU/iDMA/DDR E3.

## Model-family boundary

Qwen3.5-35B-A3B is `qwen3_5_moe`: 30 GDN + 10 dense GQA, standard residual, 256/top-8, 60 MiB GDN state and 5 GiB BF16 KV at 262k context.

Qwen3.8-Flash-Next is `qwen4_exp`: 36 GDN + 12 QSA, four-branch residual, PLE, 512/top-10, 108 MiB GDN state, 6 GiB QSA KV and 192 MiB compressed index. Do not infer ordinary Qwen3.8 support from this profile.
