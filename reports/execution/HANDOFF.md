# Local-agent handoff v7.12 — main only

## Gate

```text
L5.2 5-stage/5-context Matrix       PASS H3, WNS +0.00490451 ns
L5.3 Attention numerical/stress     PASS, score/probability DDR 0/0
L5.4 fused SiLU                     PASS, one lane, producer stall 0%
L5.5 balanced 8x8 SFU               PASS E1/E4
L5.5 composed real-RTL E3            PASS_REVIEW, 321.869395 token/s
```

## L5.5 E3 evidence

```text
controller: 12,672 tasks, Matrix 5,018,112 cycles, SFU 5,168,256 cycles
queues: Matrix 8,651 bubbles, SFU/event 4,127 bubbles
fabric: 1,478,660 L2 transactions, 126,875 bank conflicts
upstream iDMA: 1 MiB, 16,384/16,384 continuous read/write beats
DDR model: read 93,585,408 B at 0.64 efficiency; write 1,048,576 B at 1.0
28-layer calibrated cycles: 3,181,414,628
q1024 @1GHz: 321.869395 token/s; review floor 315 PASS
```

Evidence: `reports/execution/l5_5_q1024_e3_result.json`.

Boundary: production controller + production L3 fabric + pinned upstream iDMA.
This is composed real-RTL E3, not one monolithic payload numerical simulation.

## Upstream integrity

Canonical AHA, Chipyard/Gemmini, iDMA, AXI, common_cells and IMAX3 checkouts
are clean and commit/submodule locked. `Gemmini.sv`, `garnet.v` and the iDMA
backend match tracked SHA256 locks; no upstream or generated RTL was hand-edited.
Run `./scripts/run_local_gate.sh` before local gates. The old non-canonical
`work/upstream/chipyard` checkout is explicitly excluded.

## Unique next action

Run L5.6 q1024 28-layer full-model trace with frozen Qwen2 revision, all blocks,
final RMSNorm and last-token LM head. Require at least 300 token/s before L5
closure. Do not reopen 8x8 unless the accepted 315-t/s stop rule later fails.

## Execution

Use `taskset -c 8-23`, MemoryHigh=24G, MemoryMax=30G, each task <=600 s.
Remain on `main`; no force push. Preserve the two untracked AHA runtime scripts.
