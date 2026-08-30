# Gap to the final CNN/LLM accelerator target

## Current position

L0-L3 are closed. L5.1 is closed at component level. Revision 8B-B closes the Matrix functional contract at five stages/five contexts, but physical closure has not started. L5.3 and L5.4 now have bounded sandbox decisions, not RTL closure. There is still no integrated E3 run and no accepted top-level E4.

## Remaining mandatory work

| Area | Remaining closure |
|---|---|
| L4 CNN/AHA | Garnet generation/map/PnR, depthwise/layout/quant E1, 1 GHz E4, CNN subset integration |
| L5.2 Matrix | 8B-B lane, broadcast, equivalence, cluster, front and H3 E4; post-map million-step and adversarial E1; area/power delta |
| L5.3 Attention | Real blocked QK -> Block128 Softmax -> PV RTL, q128/q384/q1024 E1/E2, GQA reuse, no score/probability DDR |
| L5.4 SiLU | 1/2-lane LUT RTL, numerical E1/E2, mapped area/timing/power, Matrix stall measurement |
| L5.5 integrated E3 | Matrix/SFU/Sequence-Memory/iDMA/DDR queues, bank conflicts, outstanding requests, real service curves |
| L5.6 Qwen2 | 28-layer q1024 >=300 token/s at 1 GHz, <=4 MiB SRAM, <=100/40 GB/s DDR, numerical and E4 closure |
| L6 quantization | Exact GGML Q8_0/Q6_K/Q3_K/FP16/W8/W4/KV-INT8 contracts, unified operand frontend and mapped RTL |
| L7 Sequence Memory | Page walker, TLB/MSHR, COW/refcount/epoch, out-of-order DMA, continuous batching, E1/E3 |
| L8 Qwen3.5/Qwen3.8 | Official-weight trace; GDN/QSA/GR/PLE/MoE/MTP backends; state transaction; E1/E2/E3 |
| L9 llama.cpp | Real GGUF load, graph partition, automatic segment lowering, device submission, CPU fallback, token generation |
| L10/L11 | SRAM macro integration, STA, SAIF, PVT/Vt sweeps, post-route margin and final Pareto/signoff |

## Distance assessment

The project has a substantial architecture/compiler/reference foundation, but is not near final signoff. Four of twelve canonical stages are closed. The first major end-to-end milestone is the joint closure of L5.2/L5.3/L5.4, followed by L5.5 integrated E3. Until then, 300 token/s, Qwen3.8 throughput and power are unproven.

## Further sandbox-independent backlog

1. Exact GGML quantization formats and unified operand-frontend reference.
2. Descriptor policy macro-lowering into Command128/event programs.
3. Sequence Memory MSHR/outstanding/reorder cycle model.
4. 48-layer tensor liveness and descriptor-root validation.
5. llama.cpp mock graph-pattern and fallback regression.
6. Official Qwen3.5/Qwen3.8 trace schema and replay validator.
