# Local-agent handoff v6.8

State: **no newer local-agent push was present at the v6.8 audit**. L5.2 remains
closed at the Revision8B-B component/H3 boundary. L5.3 is still the primary
local action; L5.4 runs in parallel.

## Primary local action: L5.3

Implement real streaming `QK -> Block128 FP32 M/L/O -> PV` with Q tile 16,
K/V tile 32, Block128, GQA 6:1, Score FIFO 2 and Probability FIFO 2. Use the
existing numerical and cycle reports. Close q128, q384, reviewed q1024 rows,
43,008 q1024 merges, random Matrix/SFU backpressure, zero score/probability DDR
writes, no loss/reorder/deadlock, and measured service curves.

## Parallel local action: L5.4

Implement the 128-entry FP16 direct-SiLU LUT and fused `SiLU(gate)*up` as
1-lane and 2-lane II=1 candidates. Select one lane only when measured Matrix
producer stall is <=2%; otherwise select two. Record numerical E1, WNS,
area/power, queue high-water and producer stall.

## New v6.8 source-ready contracts

- Quant frontend: 16-value beats for FP16/Q8_0/Q6_K/Q3_K, shared dot lanes and
  post-dot scale. No format-specific multiplier arrays.
- State transaction: ten domains, out-of-order acknowledgements, atomic
  accepted-prefix barrier, epoch/generation and stale-response filtering.
- Official trace: deterministic tensor/state schema and offline replayer.
- GGML adapter: versioned raw-node/tensor ABI into the existing model-agnostic
  graph partitioner; unknown nodes remain explicit CPU fallback.
- L5.5 review: baseline 338.25 t/s, review scenario 329.83 t/s. If measured
  pre-route projection is below 315 t/s, stop and reopen the performance budget.

These are E0/source contracts. They do not replace RTL E1, integrated E3,
official-weight execution, real llama.cpp linkage or post-route signoff.
