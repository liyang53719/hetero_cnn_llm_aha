# Canonical architecture and execution plan v5

## Evidence boundary

E0 is functional/algorithmic/compiler/architecture execution; E1 is real kernel RTL simulation; E2 is sampled multi-engine numerical integration; E3 is integrated queue/DMA/SRAM/DDR cycle execution; E4 is post-synthesis timing/area/power. Source readiness is not E1, and a passing E1 with negative WNS is not E4.

## Audited local state

Commit `b8f8eaff6a323a6303a52b01db6a776ddbe9e406` closes Block128 E1: 132 bit-exact vectors, 128-lane/32-beat stream and random backpressure pass. CLN22UL 1.0 ns has zero unmapped cells but WNS `-0.555804 ns`; L5.1 therefore remains E4 FAIL_TIMING.

## L5 serial critical path

1. Validate HardFloat raw/round FP32 multiply/add pipelines with 1024 vectors.
2. Run the `_rawpipe` Block128 candidate against the retained 132-vector/32-beat gate.
3. Require CLN22UL WNS >= 0 before promotion; do not use false paths, lower frequency or multicycle exceptions.
4. Compile `bf16_outer_product_context_array.sv` against the real 512-lane array and close 1M dependent steps, backpressure, II=1 and 1 GHz timing.
5. Continue blocked QK/online-Softmax/PV, SiLU DSE, DMA overlap and 28-layer q1024 >=300 token/s.

## Qwen3.8 E0 architecture closure

The sandbox now implements append-time 4-token QSA block summaries, bounded Top-512 without full score materialization, selected-page coalescing/restoration, a cross-state MTP transaction over KV/GDN/QSA/PLE/hyper streams, official-shape MAC/state/DDR budgets, synthetic PLE/MoE cache DSE, format screening and a 4 MiB liveness candidate.

Planning results:

```text
fixed MAC/token                         6.147688448 G
q1024 average MAC/token                 6.224044544 G
BF16 512 MAC/cycle @300 t/s             infeasible
W8 2048 MAC/cycle @300 t/s              91.17% wall utilization
4096 MAC/cycle dual-W8/native-W4         45.59% wall utilization
GDN FP32 state                          108 MiB/sequence
QSA compressed index @262144            192 MiB
QSA BF16 K/V @262144                    6 GiB
```

Thus Qwen3.8 retains the Matrix/SFU arithmetic core but adds a Sequence Memory Complex, QSA Selection Engine, PLE sparse-row fetch, route-aware W4 expert path and a cross-engine transaction manager. `arch_v2_qwen38_candidate.yaml` is not canonical until E3/E4.

## Global order

```text
L4 legal AHA CNN sidecar
L5 Qwen2 BF16 q1024 >=300 t/s
L6 W8/W4/KV-INT8
L7 production paged KV + Sequence Memory Complex
L8 Qwen3.5/Qwen3.8 official traces and backends
L9 llama.cpp backend
L10 SRAM/DC/STA/SAIF
L11 fixed-environment DSE/signoff
```
