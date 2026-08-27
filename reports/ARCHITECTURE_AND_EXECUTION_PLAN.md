# Canonical architecture and execution plan v4

## 1. Implemented architecture

The repository now tracks the hardware that is actually being built:

```text
retained Gemmini INT8/CNN Matrix path
+ clean-room 16x32 BF16/FP32 LLM Matrix path
+ fixed-function Attention/Norm/SFU path
+ legal 4x4 ratio-2 Stanford AHA sidecar
+ paged KV/iDMA state engine
+ shared SRAM, streams, events and scheduler
```

The impossible `4x4 compute + 16 Lake` topology is retired. The production AHA
point is `4x4 ratio-2 = 8 PE + 8 Lake`, with additional wrapper-owned SRAM.
Performance-critical Norm, RoPE, online Softmax, M/L/O merge and SiLU remain in
fixed-function SFU RTL rather than being forced through Garnet.

## 2. Evidence classes

| Class | Meaning |
|---|---|
| E0 | Functional, algorithmic or compiler reference executed in software |
| E1 | Real kernel RTL simulation with numerical and protocol checking |
| E2 | Sampled multi-engine numerical integration |
| E3 | Integrated queue/DMA/SRAM/DDR cycle execution |
| E4 | Post-synthesis timing, area and power evidence |

A source file is not E1. A descriptor recognized by the decoder is not an
implemented backend. A tiny E0 model is not official-weight end-to-end
inference. A hard-coded service-time replay is not E3.

## 3. Sandbox-closed work

### L5 foundations

- Universal block-128 M/L/O reference, 43,008 q1024 merges and no score matrix.
- 132 frozen M/L/O vectors and an independent C++20 bit-exact reference.
- Streaming M/L/O merge RTL source and Matrix-context scoreboard source.
- Exact q1024 wall-MAC budget; the 300 token/s gate requires about 0.794 wall
  utilization, not merely high active utilization.

### L7 paged KV E0

- Two-level logical addressing, 16 token/page, prefix sharing, partial-tail copy,
  copy-on-write, refcount accounting, generation checks and one-million-token
  address analysis.

### L8 Qwen3.5/Qwen3.8 executable references

Qwen3.5 common operators now have executable E0 references for recurrent GDN,
chunk-prefill GDN, causal conv, routed/shared MoE and MTP commit/rollback.

Qwen3.8-Flash-Next now has a **stateful text-only tiny executable model**, not
only descriptors. It executes:

```text
four-branch Gated Residual read/write
PLE bigram/trigram hash and lazy embedding lookup
PLE projection, signed-sqrt gate and dilated depthwise Conv1D
Gated DeltaNet recurrent decode
Gated DeltaNet chunk-prefill algebra
QSA compressed-block indexer and top-k selection
sparse causal QK -> online Softmax -> PV
attention output sigmoid gate
routed top-k experts plus gated shared expert
MTP transactional commit/rollback
```

The frozen E0 workload runs eight tokens through the reduced
`3 x linear_attention + 1 x qwen_sparse_attention` pattern. Prefill and
incremental decode match exactly, and every executed operator has an explicit
hardware micro-op owner. Evidence:

```text
reports/execution/qwen38_text_e0_result.json
reports/execution/gdn_chunk_e0_result.json
config/qwen38_tiny_e0_contract.json
```

Official weights, the vision tower, E1 RTL, E3 throughput and E4 PPA remain
explicitly unclaimed.

## 4. Global stage order

```text
L4  legal AHA CNN sidecar closure
L5  Qwen2 BF16 q1024 >=300 token/s
L6  W8/W4/KV-INT8 and >=500 token/s quantified path
L7  production paged KV and continuous batching
L8  Qwen3.5/Qwen3.8 official traces and hybrid backends
L9  llama.cpp automatic backend
L10 SRAM/DC/STA/SAIF physical closure
L11 fixed-environment architecture sweep and signoff
```

L5 remains the serial critical path. L8 E0 development can proceed in parallel,
but must not weaken L5 gates or consume E1/E4 claims.

## 5. Immediate local critical path

```text
L5.1 Block128 RTL simulation + early 1GHz DC
 -> L5.2 lane-local Matrix context integration + 1M dependent steps + DC
 -> L5.3 blocked QK/online-softmax/PV integration
 -> L5.4 1/2/4/8-lane fused SiLU-times-up DSE
 -> L5.5 real queue/DMA/DDR overlap
 -> L5.6 28-layer Qwen2 q1024 E2/E3/E4 closure
```

## 6. Qwen3.8 local backend sequence

The E0 model fixes numerical and state contracts. Local implementation is split
into independently reviewable gates:

1. **L8.1 official node trace**: obtain the frozen model/config/weights and emit
   per-layer QSA, GDN, GR, PLE, MoE and MTP tensors from Transformers or
   llama.cpp.
2. **L8.2 GDN backend**: causal-conv state, Q/K L2Norm, decay/beta generation,
   recurrent state update, chunk-prefill and gated RMSNorm/out projection.
3. **L8.3 QSA backend**: index-key cache, compressed-block pooling, top-k,
   sparse gather, block-128 online Softmax/PV and output gate.
4. **L8.4 GR/PLE backend**: four residual branches, low-rank read gates,
   injection gates, n-gram hash/lookup/prefetch and dilated conv state.
5. **L8.5 MoE/MTP backend**: router, expert batching/cache, grouped GEMM,
   weighted reduce, shared expert and speculative state transaction.
6. **L8.6 official text closure**: one block, four-layer pattern, 48-layer text
   trace, then performance and physical evidence.

Each gate must preserve a CPU fallback until its own E1/E2 result is committed.
