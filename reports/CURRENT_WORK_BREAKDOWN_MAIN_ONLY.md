# Current work breakdown on consolidated main

## Closed and accepted

- L0 control/provenance.
- L1 upstream Gemmini/AHA/iDMA baselines.
- L2 wrapper-only integration.
- L3 shared SRAM/fabric/event contracts.
- L5.1 Block128 E1/component E4, with effectively zero timing margin.
- L5.2 Revision8B-B 512-lane, five-stage/five-context Matrix E1, mapped compare,
  component DC, structural H3 and post-map E1.
- L5.3a Blocked Attention controller E1/DC: WNS `+0.00191498 ns`, area
  `1773.408002` library units.
- L5.4 one-lane and two-lane fused-SiLU candidates E1/DC/PPA:
  - one lane WNS `+0.0000521541 ns`, area `10559.276031`;
  - two lane WNS `+0.0000220537 ns`, area `19747.364067`.
- Sandbox E0/source contracts for full Attention, exact GGML formats, unified
  quant frontend, state transactions, trace capture and graph partition.

Vectorless DC power numbers are screening estimates, not SAIF evidence.

## Tasks that require local-agent output

1. L5.3b: connect controller to real Revision8B-B QK/PV and Block128 FP32 M/L/O;
   close q128/q384/q1024 numerical E2 and measured service curves.
2. L5.4 selection: measure Matrix producer stall and choose one lane when
   stall <=2%, otherwise two lanes; rerun the selected integrated path.
3. L5.5: real Matrix/SFU/iDMA/DDR E3 with queue, bank, byte and event counters.
4. L5.6: 28-layer q1024 >=300 token/s, <=4 MiB SRAM, <=100/40 GB/s DDR.
5. L4: Garnet map/PnR/bitstream, CNN kernels, Gemmini/AHA integration and E4.
6. L6: pinned llama.cpp parity, quant frontend/shared-dot RTL and PPA.
7. L7: Page Walker/TLB/MSHR/COW/refcount/epoch RTL and AXI/iDMA E3.
8. L8: official immutable traces and Qwen3.5/Qwen3.8 backend E1/E2/E3.
9. L9: real llama.cpp/GGUF adapter, device submission, fallback and token run.
10. L10/L11: SRAM macros, post-route STA, PVT/OCV, SAIF power and Archspec
    promotion.

## Tasks that can continue without local-agent results

- Generate larger q128/q384/q1024 Attention metadata and sampled numerical
  vector packs for the integrated E2 harness.
- Extend fused-SiLU vectors with zero, subnormal, boundary, infinity and NaN
  class tests and refine producer-stall models.
- Extend Q8_0/Q6_K/Q3_K/FP16 frontend K-tail and shared-dot scheduling vectors.
- Expand State Commit Barrier assertions, COW/refcount/dirty-mask vectors and
  stale-response adversarial cases.
- Extend trace/replayer and model-agnostic GGML adapter regression using the
  tiny executable Qwen3.8 model.
- Refine L5.5 sensitivity sweeps and generate the minimum E3 test matrix.
- Maintain Archspec collateral and evidence consistency on main.

## Nearest milestone

```text
L5.3 full Attention E2 + L5.4 measured lane selection
        -> L5.5 real integrated E3
        -> L5.6 q1024 >=300 token/s
```
