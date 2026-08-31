# Final target gap v7.0

## Closed or accepted

- L0-L3 control, upstream, wrapper and shared-fabric baselines.
- L5.1 Block128 E1/component E4, with effectively zero timing margin.
- L5.2 Revision8B-B 512-lane, five-stage/five-context Matrix E1, mapped comparison, component DC, structural H3 and post-map E1.
- L5.3 Controller and Block32-weight component gates; full single-simulation numerical Attention remains open.
- L5.4 one- and two-lane fused-SiLU standalone candidates; integrated producer-stall selection remains open.
- E0/source contracts for Attention vectors, low-bit formats/tails, state transactions, trace capture, graph partition and the minimum E3 matrix.

## Nearest Qwen2 milestone

1. Run one integrated q128 simulation containing Controller, Revision8B-B QK/PV, Block32 weights and Block128 M/L/O; then q384 and reviewed q1024 rows.
2. Freeze the SiLU special-value contract, measure Matrix producer stall and select one or two lanes; rerun the selected integrated path.
3. Run the 11-case Matrix/SFU/iDMA/DDR E3 matrix with measured queue, bank, byte and event counters.
4. Run 28-layer q1024 at at least 300 token/s, no more than 4 MiB SRAM and no more than 100/40 GB/s DDR read/write.

## Remaining global work

- CNN/AHA: legal Garnet mapping/PnR/bitstream, kernels, Gemmini integration, numerical closure and 1 GHz E4.
- Quant: pinned llama.cpp parity, shared frontend/dot RTL, W8/W4/KV INT8/FP8 and PPA.
- Serving state: Page Walker/TLB/MSHR/COW/refcount/dirty mask/epoch, OOO iDMA/AXI and continuous batching.
- Qwen3.5/Qwen3.8: official immutable traces, GDN/QSA/GR/PLE/MoE/MTP backends and 48-layer E3.
- Software: real llama.cpp/GGUF graph capture, tensor binding, command submission, fallback and end-to-end token generation.
- Signoff: SRAM macros, post-route STA, PVT/OCV, SAIF power, nontrivial margin and final Archspec/Pareto promotion.
