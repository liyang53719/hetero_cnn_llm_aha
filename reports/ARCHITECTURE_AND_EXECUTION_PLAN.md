# Canonical architecture and execution plan v6.10 + sandbox v7.0 extension

## Frozen architecture

```text
Retained Gemmini INT8/CNN Matrix
+ Revision8B-B clean-room BF16/FP32 Matrix
+ fixed-function Attention/Norm/SFU
+ legal Stanford AHA 4x4 ratio-2 sidecar
+ Sequence Memory Complex / iDMA
+ shared 4 MiB SRAM and Command128/event fabric
```

The Matrix remains frozen at 16x32/512 lanes, five FMA stages and five accumulator contexts. L5.1/L5.2 are component/H3 closures, not post-route signoff.

## Active L5 path

### L5.3 full Attention

The Controller, trace bridge and Block32-weight component gates pass. The remaining gate is one integrated QK -> FP32 M/L/O -> PV simulation. The frozen vector pack is `reports/execution/attention_e2_vector_pack_result.json`:

```text
q128  all 1,536 rows
q384  180 fixed boundary rows
q1024 108 fixed rows across boundary heads
q1024 merge rows 43,008
```

Score and probability DDR materialization remains forbidden.

### L5.4 fused SiLU

One- and two-lane standalone candidates pass E1/DC. Final selection requires measured Matrix-producer stall. Before selection, freeze the special-value policy in `reports/SILU_EDGE_POLICY_REVIEW_V7_0.md`; source changes require rerunning both candidates.

### L5.5 join

Use the 11-case matrix in `reports/execution/e3_minimum_matrix.json`. Collect measured Attention/SiLU service, queue, bank, DDR and event counters. Below 315 token/s pre-route projection, reopen the budget rather than proceeding on a 300 token/s edge.

## Parallel sandbox/source-ready work

- FP16/Q8_0/Q6_K/Q3_K 16-value K-tail scheduler and source-ready RTL.
- 5,000 adversarial state transactions with OOM, timeout, stale/duplicate acknowledgement and generation-wrap coverage.
- Official trace schema and model-agnostic GGML adapter.

## Remaining order

```text
L5.3 single-sim Attention E2 + L5.4 selected SiLU
  -> L5.5 real Matrix/SFU/iDMA/DDR E3
  -> L5.6 28-layer q1024 >=300 t/s
L4 CNN/AHA
L6 pinned GGML parity and low-bit RTL
L7 production Sequence Memory E1/E3
L8 Qwen3.5/Qwen3.8 official traces/backends
L9 real llama.cpp/GGUF
L10 post-route/PVT/SAIF
L11 final Archspec/Pareto
```
