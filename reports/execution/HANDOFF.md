# Local-agent handoff v7.15 — main only

## Gate

```text
L5.2 5-stage/5-context Matrix       PASS H3, WNS +0.00490451 ns
L5.3 Attention numerical/stress     PASS, score/probability DDR 0/0
L5.4 fused SiLU                     PASS, one lane, producer stall 0%
L5.5 balanced 8x8 SFU               PASS E1/E4
L5.5 composed real-RTL E3            PASS_REVIEW, 321.869395 token/s
L5.6 28-layer count/trace E3         PASS, 321.085777 token/s
L5.6 reduced four-layer cross RTL    PASS, 7,840/7,840 bit-exact
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

The same RTL count/trace controller emitted 28 blocks, final RMSNorm and one
last-token LM head: 3,189,178,948 cycles, 3,087,138,816 read bytes and
29,967,872 write bytes. SRAM=4 MiB and Revision8B-B H3 WNS=+0.00490451 ns.

Exact-revision Qwen2 weights are locally locked at SHA256 `302e3277...e9057`.
The q1024 four-layer PyTorch reference passes; last-token logits hash is
`20247ec3...e877822`. Revision8B-B replays 160 official LM-head columns:
FP32 accumulator -> BF16 RNE is 160/160 bit-exact, max error 0, argmax 54387.

Reduced cross-layer RTL now covers layer0-3 input RMSNorm/Q samples and layer3
post-attention RMSNorm/gate samples under random backpressure. RMS 7,680 values
and Matrix 160 samples are bit-exact. Refined rsqrt is a 54-cycle FSM using the
accepted 1 GHz FP32 pipelines; DC WNS is +0.000101328 ns, area 4,136.314.

Adjusted q1024 full trace is 3,192,103,543 cycles = 320.791599 token/s.
Next: L10 early PPA. This does not claim full q1024 payload RTL or post-route.

## Execution

Use `taskset -c 8-23`, MemoryHigh=24G, MemoryMax=30G, each task <=600 s.
Remain on `main`; no force push. Preserve the two untracked AHA runtime scripts.
