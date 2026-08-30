# Final target gap v6.6

## Closed now

- L0-L3 control, upstream, wrapper and shared-fabric baselines.
- L5.1 Block128 component E1/E4.
- L5.2 Revision8B-B 512-lane Matrix functional and component/H3 physical gate.
- Extensive E0 references for CNN/LLM operators, Qwen3.5/Qwen3.8, Sequence
  Memory, Archspec and mock backend.

## Required before the first credible Qwen2 system claim

1. L5.3 real QK/Block128/PV E1/E2.
2. L5.4 fused SiLU 1/2-lane E1/E4 selection.
3. L5.5 integrated Matrix/SFU/iDMA/DDR E3 with real queue/bank/traffic data.
4. L5.6 28-layer q1024 execution at >=300 token/s, <=4 MiB SRAM and
   <=100/40 GB/s external read/write.

## Required for CNN support

- legal AHA Garnet mapping/PnR/bitstream and real Depthwise/Layout/Quant E1;
- Gemmini/CNN integration and 1 GHz physical closure.

## Required for production quantized inference

- byte-exact Q8_0, Q6_K, Q3_K and FP16/GGUF layouts;
- shared physical dot array operand frontends;
- W8/W4/KV INT8/FP8 RTL, numerical regression and PPA.

## Required for long-context serving

- page walker, TLB, MSHR, COW/refcount/epoch RTL;
- out-of-order iDMA/AXI integration and continuous batching E3;
- cross-engine MTP state commit/rollback.

## Required for Qwen3.5/Qwen3.8

- official immutable-revision node traces;
- GDN, QSA, GR, PLE, MoE and MTP backend E1/E2;
- 48-layer text E3 and performance/traffic closure.

## Required for software usability

- real llama.cpp/GGML graph matcher and automatic partition;
- GGUF tensor binding, device memory, command submission and CPU fallback;
- end-to-end token generation without model-specific handwritten operator code.

## Final physical signoff

- SRAM macro integration;
- post-route STA with PVT/OCV and nontrivial margin;
- SAIF-based power;
- final area/performance/power Pareto and Archspec promotion.

The project has crossed the main BF16 Matrix feasibility barrier, but has not
yet crossed the first integrated E3 system barrier. L5.5 is now the most
important milestone after L5.3/L5.4.
