# Final target gap v6.8

## Closed

- L0-L3 control, upstream, wrapper and shared-fabric baselines.
- L5.1 Block128 component E1/E4, with effectively zero timing margin.
- L5.2 Revision8B-B 512-lane Matrix E1 and component/H3 DC at 1 GHz.
- E0/source contracts for Blocked Attention, fused SiLU, exact GGML formats,
  unified quant operand beats, Sequence Memory/state transactions, Qwen3.5/
  Qwen3.8 compiler inventory, trace schema and graph partition.

## Nearest system milestone

1. L5.3 real QK -> Block128 M/L/O -> PV E1/E2.
2. L5.4 fused SiLU 1/2-lane E1/E4 selection.
3. L5.5 real Matrix/SFU/iDMA/DDR E3 with measured counters. A pre-route
   projection below 315 t/s reopens the performance budget.
4. L5.6 28-layer q1024 >=300 t/s, <=4 MiB SRAM and <=100/40 GB/s read/write.

## Remaining major programs

- CNN/AHA: legal Garnet map/PnR/bitstream, Depthwise/Layout/Quant E1, Gemmini
  integration and 1 GHz closure.
- Quant: pinned llama.cpp parity, unified decoder/shared-dot RTL, W8/W4/KV
  INT8/FP8 regression and PPA.
- Serving state: page walker/TLB/MSHR, atomic COW/refcount/epoch, OOO iDMA/AXI,
  continuous batching and MTP commit/rollback E1/E3.
- Qwen3.5/Qwen3.8: immutable official traces; GDN/QSA/GR/PLE/MoE/MTP backends;
  48-layer text E3 and traffic/performance closure.
- Software: real llama.cpp/GGUF graph capture, tensor binding, command
  submission, CPU fallback and end-to-end token generation.
- Signoff: SRAM macros, post-route PVT/OCV, SAIF power and final Archspec/Pareto
  promotion.

The project has crossed the BF16 Matrix feasibility gate but not the first
integrated heterogeneous E3 gate. L5.3/L5.4 -> L5.5 remains the critical path.
