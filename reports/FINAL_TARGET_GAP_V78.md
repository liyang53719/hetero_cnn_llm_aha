# Final target gap v7.8

## Accepted

- L0–L3 control, upstream, wrapper and shared-fabric baselines.
- L5.1 Block128 and L5.2 Revision8B-B Matrix component/hierarchical gates.
- L5.3 Attention numerical/stress service and zero score/probability DDR materialization.
- L5.4 selected one-lane fused SiLU.
- L5.5 balanced 8×8 E1/E4 and composed real-RTL E3 at 321.869395 token/s.
- L5.6 28-layer count/trace E3 at 320.791599 token/s, official reference checkpoints, sampled LM-head RTL and reduced four-layer cross RTL.

## Open claim boundary

A continuous 28-layer q1024 payload numerical RTL replay has not been shown. L10 early PPA is allowed to proceed in parallel, but neither L5.6d nor post-route signoff is closed.

## Nearest local gates

1. hierarchy-preserving integrated synthesis with no area double-count;
2. 4 MiB SRAM macro replacement and bank/port validation;
3. seven continuous four-layer payload groups, then a continuous 28-layer or real-backend equivalent replay;
4. post-route setup/hold, PVT/OCV and workload-derived SAIF.

## Remaining project goals

- L4: legal Stanford AHA/Garnet CNN kernels, mapping, PnR, bitstream and integration.
- L6: pinned llama.cpp FP16/Q8_0/Q6_K/Q3_K parity, shared multi-format dot RTL, W8/W4/KV INT8/FP8 and PPA.
- L7: production Page Walker/TLB/MSHR/COW/refcount/dirty/epoch, OOO iDMA and continuous batching.
- L8: official Qwen3.5 and Flash-Next traces and GDN/Attention/QSA/PLE/GR/MoE/MTP backends.
- L9: real GGML/GGUF graph/tensor binding, command submission, fallback and end-to-end tokens.
- L10: SRAM macros, post-route STA, PVT/OCV and SAIF power.
- L11: measured architecture Pareto, canonical Archspec and release signoff.
