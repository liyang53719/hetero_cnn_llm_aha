# Local-agent handoff v6.10 — main only

## Git workflow is now a hard gate

Remote audit found exactly one branch: `main`. The accepted local-agent commit
`eba24625350d14fe3f9d760929736dcf5872fabd` is already in the ancestry of the
current main line. There is nothing to merge or delete.

Local Agent must not create another branch. Before work:

```bash
git fetch --prune origin
git checkout main
git pull --ff-only origin main
./scripts/check_main_only_workflow.sh
```

Before push, fetch again. If `origin/main` advanced, rebase the local main commit
onto it, rerun affected gates and push fast-forward. Force-push, PR branches,
`git checkout -b` and `git switch -c` are forbidden unless the user explicitly
authorizes an exception.

## Closed boundary

```text
L5.1 Block128                    PASS, component WNS +0.0000136495 ns
L5.2 Matrix Revision8B-B         PASS at component/H3 boundary
Array / stages / contexts       16x32 / 5 / 5
H3 WNS                          +0.00490451 ns
H3 DRC / unmapped / unresolved  0 / 0 / 0 / 0
```

Post-route, PVT/OCV and power remain L10 risks.

## Local-dependent primary work

### L5.3

```bash
./scripts/sandbox_validate.sh
./scripts/run_l5_blocked_attention_controller_e1.sh
./scripts/run_l5_blocked_attention_controller_dc.sh
```

Then connect the controller to Revision8B-B QK/PV and Block128 FP32 M/L/O.
Close q128/q384/q1024 numerical/service E1/E2, exactly 43,008 q1024 merge rows,
random Matrix/SFU backpressure and zero score/probability DDR writes.

### L5.4 in parallel

```bash
./scripts/run_l5_silu_lut_e1.sh
./scripts/run_l5_silu_lut_dc.sh
```

Compare one and two lanes. Select one lane when measured Matrix-producer stall
is <=2%, otherwise two lanes. Record numerical E1, WNS, area, power, queue
high-water and producer stall.

L5.5 remains the mandatory join after full L5.3 and L5.4 PASS.

## Sandbox-independent work

Continue vector generation, quant frontend contracts, state-transaction
assertions, trace/replayer regressions, GGML node-adapter tests, E3 sensitivity
analysis and Archspec collateral directly on main. None of those results may be
reported as local E1/E2/E3/E4 evidence.
