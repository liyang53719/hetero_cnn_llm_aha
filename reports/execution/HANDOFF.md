# Local-agent handoff v6.10 — main only

## Git workflow hard gate

Remote audit found exactly one branch: `main`. Do not create another local or
remote branch. Before work:

```bash
git fetch --prune origin
git checkout main
git pull --ff-only origin main
./scripts/check_main_only_workflow.sh
```

Before push, fetch again; rebase local main if origin/main advanced, rerun all
affected gates and push fast-forward. Force-push and PR branches are forbidden.

## Accepted closures

```text
L5.1 Block128                   PASS, WNS +0.0000136495 ns
L5.2 Matrix Revision8B-B        PASS, H3 WNS +0.00490451 ns
L5.3 Controller E1/DC           PASS, WNS +0.00191498 ns, area 1773.408002
L5.4 one-lane E1/DC             PASS, WNS +0.0000521541 ns, area 10559.276031
L5.4 two-lane E1/DC             PASS, WNS +0.0000220537 ns, area 19747.364067
```

All margins are very small. Power numbers are vectorless DC estimates, not
SAIF evidence.

## Unique next action

Connect `blocked_attention_stream_controller` to Revision8B-B QK/PV and the
existing FP32 Block128 M/L/O path. Close q128 full numerical E2 first, then
q384 and reviewed q1024 rows with exactly 43,008 merges. Measure q128/q384/q1024
service curves under random Matrix/SFU/output backpressure and prove score and
probability DDR writes remain zero.

Use the same integration run to measure Matrix producer stall. Select the
one-lane SiLU implementation when stall is <=2%; otherwise select two lanes.
Rerun the selected integrated path before declaring L5.4 complete.

L5.5 remains the mandatory join.
