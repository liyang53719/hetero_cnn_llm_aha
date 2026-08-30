# Final target gap v6.7

## Closed

- L0-L3 control/upstream/wrapper/shared-fabric baselines.
- L5.1 Block128 component E1/E4, with essentially zero timing margin.
- L5.2 Revision8B-B 512-lane, five-stage/five-context Matrix E1 and component/H3
  DC at 1 GHz; post-route/PVT margin remains L10 risk.
- E0 references for Qwen2/Qwen3.5/Qwen3.8 operators, compiler inventory,
  Sequence Memory, Archspec, QSA, MTP, GGML quant layouts and graph partition.

## Nearest system milestone

The first credible Qwen2 system claim still requires:

1. L5.3 real QK -> Block128 M/L/O -> PV E1/E2.
2. L5.4 fused SiLU 1/2-lane E1/E4 selection.
3. L5.5 real Matrix/SFU/iDMA/DDR E3 using measured service curves and queue,
   bank, byte and event counters.
4. L5.6 28-layer q1024 >=300 token/s, <=4 MiB SRAM and <=100/40 GB/s read/write.

## CNN

Legal Garnet 4x4 ratio-2 mapping/PnR/bitstream, Depthwise/Layout/Quant E1,
Gemmini integration, CNN subset numerical closure and 1 GHz physical closure.

## Quantized production path

Pinned llama.cpp parity for Q8_0/Q6_K/Q3_K/FP16, W8/W4/KV INT8/FP8 RTL,
shared dot-array operand frontends, numerical regression and PPA.

## Serving state

Page walker/TLB/MSHR RTL, atomic COW/refcount/epoch, OOO iDMA/AXI, continuous
batching and cross-engine MTP transaction commit/rollback E1/E3.

## Qwen3.5/Qwen3.8

Official immutable-revision traces; GDN, QSA, GR, PLE, MoE and MTP backend
E1/E2; 48-layer text E3 and bandwidth/performance closure.

## Software and signoff

Real llama.cpp/GGUF graph adapter, tensor binding, command submission, CPU
fallback and end-to-end token generation; SRAM macros, post-route PVT/OCV,
SAIF power and final Archspec/Pareto promotion.
