# Current work breakdown on consolidated main

## Closed and accepted

- L0 control/provenance and validation framework.
- L1 upstream Gemmini/AHA/iDMA baselines.
- L2 wrapper-only integration.
- L3 shared SRAM, fabric and event contracts.
- L5.1 Block128 E1/component E4; timing margin is effectively zero and remains
  an L10 risk.
- L5.2 Revision8B-B 512-lane, five-stage/five-context BF16 Matrix E1,
  mapped-lane comparison, component DC, structural H3 and post-map E1.
- Sandbox E0/source contracts for Blocked Attention control, fused SiLU,
  exact GGML storage formats, unified quant operand frontend, Sequence State
  transactions, trace capture and model-agnostic GGML graph partition.

## Tasks that require local-agent output

1. L5.3a: elaborate, simulate and synthesize the Blocked Attention controller.
2. L5.3b: integrate real Revision8B-B QK/PV with Block128 FP32 M/L/O and close
   q128/q384/q1024 numerical/service E1/E2.
3. L5.4: run one- and two-lane fused SiLU Verilator E1 and CLN22UL E4/PPA;
   select using measured Matrix-producer stall.
4. L5.5: real Matrix/SFU/iDMA/DDR E3 with queue, bank, byte and event counters.
5. L5.6: 28-layer q1024 >=300 token/s, <=4 MiB SRAM and <=100/40 GB/s DDR.
6. L4: Garnet map/PnR/bitstream, CNN kernels, Gemmini/AHA integration and E4.
7. L6: pinned llama.cpp parity, quant frontend/shared-dot RTL and PPA.
8. L7: Page Walker/TLB/MSHR/COW/refcount/epoch RTL and AXI/iDMA E3.
9. L8: official immutable traces and Qwen3.5/Qwen3.8 backend E1/E2/E3.
10. L9: real llama.cpp/GGUF adapter, device submission, fallback and token run.
11. L10/L11: SRAM macros, post-route STA, PVT/OCV, SAIF power and Archspec
    promotion.

## Tasks that can continue without local-agent results

- Generate larger deterministic q128/q384/q1024 Attention metadata and sampled
  numerical vector packs for the local E1/E2 harness.
- Extend fused-SiLU vectors with zero, subnormal, boundary, infinity and NaN
  class tests; refine producer-stall analytical models.
- Extend Q8_0/Q6_K/Q3_K/FP16 operand frontend vectors, K-tail coverage and
  shared-dot scheduling contracts.
- Expand State Commit Barrier assertions, COW/refcount/dirty-mask transaction
  vectors and stale-response adversarial cases.
- Extend official trace schema/replayer and model-agnostic GGML node adapter
  regressions using the tiny executable Qwen3.8 model.
- Refine L5.5 sensitivity sweeps and generate the minimum local E3 test matrix;
  this remains preflight, not E3.
- Maintain Archspec collateral, task ownership, result schemas and evidence
  consistency while preserving `arch_v1` as canonical.

## Nearest system milestone

```text
L5.3 PASS + L5.4 PASS
        -> L5.5 real integrated E3
        -> L5.6 q1024 >=300 token/s
```

The project has crossed the BF16 Matrix feasibility boundary but has not yet
crossed the first real heterogeneous-system E3 boundary.
