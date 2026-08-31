# Local-agent handoff v7.11 — main only

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

## Local balanced 8x8 result

```text
tile16: nominal236, stress252 cycles, WNS +0.00011009 ns, area277390.659
merge8: nominal353, stress365 cycles, WNS +0.00000864267 ns, area357614.803
q1024 stress projection: 322.373487 t/s
unmapped/unresolved/blackbox: 0
```

Numerical/backpressure E1 and preferred>=320 projection pass. Evidence:
`reports/execution/l5_5_balanced_8x8_local_result.json`.

## Unique next action

Run real q1024 Matrix/SFU/iDMA/DDR E3 with measured queue, bank, event and DDR
counters. Require score/probability DDR=0 and >=315 t/s.

## Model-family boundary

Qwen3.5-35B-A3B is `qwen3_5_moe`: 30 GDN + 10 dense GQA, standard residual, 256/top-8, 60 MiB GDN state and 5 GiB BF16 KV at 262k context.

Qwen3.8-Flash-Next is `qwen4_exp`: 36 GDN + 12 QSA, four-branch residual, PLE, 512/top-10, 108 MiB GDN state, 6 GiB QSA KV and 192 MiB compressed index. Do not infer ordinary Qwen3.8 support from this profile.
