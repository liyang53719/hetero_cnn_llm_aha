# Final target gap v6.9

## Closed

- L0-L3 control, upstream, wrapper and shared-fabric baselines.
- L5.1 Block128 component E1/E4, with essentially zero timing margin.
- L5.2 Revision8B-B 512-lane, five-stage/five-context Matrix E1 and component/H3 DC at 1 GHz.
- E0/source contracts for Blocked Attention control, fused SiLU, GGML quant frontends, state transactions, trace capture and graph partition.

## Nearest Qwen2 milestone

1. Elaborate and pass the new Attention controller E1/DC subgate.
2. Integrate real QK -> Block128 M/L/O -> PV and pass q128/q384/q1024 E1/E2.
3. Pass one/two-lane fused SiLU E1/E4 and select by producer stall.
4. Run real Matrix/SFU/iDMA/DDR E3 with measured queue/bank/byte/event counters.
5. Run 28-layer q1024 at >=300 token/s, <=4 MiB SRAM and <=100/40 GB/s read/write.

## CNN

Legal Garnet 4x4 ratio-2 mapping/PnR/bitstream, Depthwise/Layout/Quant E1, Gemmini integration, CNN subset numerical closure and 1 GHz physical closure.

## Quantized production path

Pinned llama.cpp parity for Q8_0/Q6_K/Q3_K/FP16, shared-dot operand frontend E1/PPA, W8/W4/KV INT8/FP8 RTL and numerical closure.

## Serving state

Page walker/TLB/MSHR RTL, atomic COW/refcount/dirty bitmap/epoch, OOO iDMA/AXI, continuous batching and cross-engine MTP transaction E1/E3.

## Qwen3.5/Qwen3.8 and software

Official immutable traces; GDN/QSA/GR/PLE/MoE/MTP backend E1/E2; 48-layer text E3; real llama.cpp graph capture, GGUF binding, device submission, CPU fallback and end-to-end token generation.

## Physical signoff

SRAM macros, post-route STA, PVT/OCV, SAIF power, nontrivial timing margin and final Archspec/Pareto promotion. L5.1/L5.2 positive DC margins remain material L10 risks.
