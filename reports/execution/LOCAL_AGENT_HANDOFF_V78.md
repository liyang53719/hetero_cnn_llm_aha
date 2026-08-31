# Local-agent handoff v7.8 — main only

## First commands

```bash
git fetch --prune origin
git checkout main
git pull --ff-only origin main
./scripts/check_main_only_workflow.sh
./scripts/sandbox_validate.sh
```

Do not create a branch and do not force-push.

## Accepted boundary

```text
L5.5 balanced 8×8 component E1/E4        PASS
L5.5 composed real-RTL E3                  PASS, 321.869395 token/s
L5.6 28-layer cycle/count trace E3         PASS, 320.791599 token/s
L5.6 official reference / LM-head samples  PASS
L5.6 reduced four-layer cross RTL          PASS, 7,840 bit-exact
L5.6 full 28-layer payload numerical RTL   OPEN
```

The current main may execute L10 early PPA in parallel with the open full-payload gate. Do not report L5.6d or post-route signoff as complete.

## P0 — L10 early PPA

Run hierarchy-preserving synthesis for the accepted owner hierarchy. The result must identify whether each area figure is a leaf, frozen DDC, or parent-inclusive total. Duplicate area counting is a hard failure.

Acceptance:

```text
clock                         1.0 ns
WNS                           >= 0 ns
unmapped/unresolved/blackbox  0/0/0
non-reset data false paths    0
multicycle timing exceptions  0
transition/cap violations     0 after the approved stage
```

Then replace/integrate SRAM macros:

```text
total capacity        <= 4 MiB
owner/address overlap = 0
bank conflict counters present
macro timing arcs linked
```

Post-route/PVT/OCV and SAIF remain separate later gates.

## P1 — full-payload numerical closure

Use `reports/execution/qwen2_payload_closure_plan.json`.

Phase 1: all 168 layer/phase checkpoints.

Phase 2: seven continuous four-layer groups. Do not inject a reference hidden state inside a group. Enable random backpressure and compare each group output to the exact official checkpoint.

Phase 3: continuous 28-layer payload replay, or an equivalent real llama.cpp/device-backend execution, with no intermediate reference-state injection. Final RMSNorm and LM-head outputs must close under the frozen numerical contract.

## Required evidence commit

The same main-branch commit must contain raw-log hashes, machine-readable results, updated control/ledger/stages/final validation, and the exact source/weight revision hashes. A source-only push is not sufficient.
