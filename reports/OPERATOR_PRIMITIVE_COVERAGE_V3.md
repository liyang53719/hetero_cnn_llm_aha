# Three-model operator primitive coverage V3

## Decision

The canonical operator-primitive source is now:

```text
chisel/three_model_operator_primitives
config/model_operator_inventory_v3_complete.json
```

It defines 18 independently schedulable, synthesizable Chisel roots and a granular inventory for:

- Qwen2-1.5B: 30 operator entries;
- Qwen3.5-35B-A3B: 93 operator entries;
- Qwen3.8-Flash-Next: 150 operator entries.

The inventory includes the text path, vision encoder operator surface, multimodal feature injection, MTP state transaction and deterministic argmax. Tokenization and host sampling policy are outside the hardware model-operator surface.

The completed gate is:

```text
PASS_COMPLETE_THREE_MODEL_CHISEL_OPERATOR_PRIMITIVE_SOURCE_GATE
```

This means every required model operator is bound to a Chisel root; the root emits a finite descriptor-driven leaf-operation sequence; launch/issue/completion/result ready-valid behavior is implemented; critical operator ordering is checked; and the project can be independently compiled and emitted without Chipyard.

It does **not** mean integrated numerical RTL, Command128-to-payload transport or DC timing is complete. Those are the next local-agent gates.

## V3 corrections relative to the earlier coarse primitive set

V3 makes five material corrections:

1. Qwen3.8 hyper-connection read implements the full learned path:

```text
group RMSNorm
  -> low-rank down
  -> 1 / branch-count scale
  -> SiLU
  -> low-rank up
  -> sigmoid
  -> branch-weighted reduction
```

2. Hyper read and hyper write/inject are separate roots. Attention and MoE may checkpoint, stall and roll back their stream transactions independently.

3. Token input embedding, final normalization, LM-head/argmax and MTP draft/resolve are separate launches. No input embedding operation is implicitly reused as an LM head.

4. Vision is decomposed into patch projection/position interpolation, transformer block, spatial merger and multimodal scatter. There is no `vision_encoder` placeholder in the canonical inventory.

5. Gated-DeltaNet has a runtime-configured output gate. Mode bit 0 selects sigmoid; clear selects SiLU. This covers the model-family distinction without compiling separate datapaths.

## Chisel roots

| Root | Responsibility |
|---|---|
| `HeteroTokenEmbeddingPrimitiveV3` | Token embedding row lookup |
| `HeteroQwen2DecoderBlockPrimitiveV3` | Complete Qwen2 dense decoder block |
| `HeteroQwen35DenseAttentionPrimitiveV3` | Qwen3.5 dense GQA attention with Q/K norm and sigmoid output gate |
| `HeteroGatedDeltaNetPrimitiveV3` | Qwen3.5/Qwen3.8 causal convolution and delta-rule recurrence |
| `HeteroMoePrimitiveV3` | Stable Top-K, routed experts, shared expert and route reduction |
| `HeteroQwen38GatedResidualReadPrimitiveV3` | Four-stream learned read/mix |
| `HeteroQwen38GatedResidualWritePrimitiveV3` | Four-stream gated block injection and state write |
| `HeteroPlePrimitiveV3` | EOS-aware n-gram history, sparse row fetch, gate and dilated convolution |
| `HeteroQsaPrimitiveV3` | Index compression/selection, sort/coalescing and sparse attention |
| `HeteroQwen38FinalHyperMergePrimitiveV3` | Final four-stream merge and normalization |
| `HeteroVisionPatchEmbedPrimitiveV3` | 3-D patch projection and interpolated position embedding |
| `HeteroVisionTransformerBlockPrimitiveV3` | Non-causal/window attention and GELU MLP |
| `HeteroVisionPatchMergePrimitiveV3` | Configurable pre/post-shuffle norm and spatial merge |
| `HeteroMultimodalInjectPrimitiveV3` | Vision-feature gather and token-position scatter |
| `HeteroFinalNormPrimitiveV3` | Standalone Qwen2/Qwen3.5 final RMSNorm |
| `HeteroLmHeadArgmaxPrimitiveV3` | LM-head GEMV and deterministic argmax |
| `HeteroMtpDraftPrimitiveV3` | Private-generation draft state and candidate token |
| `HeteroMtpVerifyResolvePrimitiveV3` | Target comparison, accepted prefix and commit/rollback |

## Model coverage

### Qwen2-1.5B

The decoder program contains input/post-attention RMSNorm, seven dense projections, Q/K/V bias, independent Q/K RoPE, paged KV append/gather, GQA QK, scale, causal mask, online softmax, PV, residuals and SwiGLU. Final norm and language head are separate roots.

Source-level operator coverage: **30/30**.

### Qwen3.5-35B-A3B

The source gate covers:

- 30 Gated-DeltaNet layers: causal depthwise convolution, Q/K L2 normalization, query scaling, softplus/exp decay, beta sigmoid, recurrent-state decay, delta, rank-1 outer-product update, state query and gated output projection;
- 10 dense-attention layers: Q/K RMSNorm, partial interleaved MRoPE, GQA, online softmax and sigmoid attention-output gate;
- 256-expert Top-8 routed MoE plus shared expert;
- MTP draft/verify/rollback;
- patch projection, vision transformer, patch merger and multimodal injection.

Source-level operator coverage: **93/93**.

### Qwen3.8-Flash-Next

The source gate covers:

- 36 linear-attention/GDN layers with configurable output gate;
- 12 QSA layers with compressed index summaries, non-negative score clamp, head reduction, stable Top-512, selected-index sort, gather-run coalescing, sparse KV gather and sparse online attention;
- independent Attention/MoE four-stream hyper read and write transactions;
- PLE n-gram history/hash, sparse embedding rows, learned key/value gate and dilated causal depthwise convolution;
- 512-expert Top-10 MoE;
- final hyper merge, MTP and the full shared vision/injection surface.

Source-level operator coverage: **150/150**.

## Active clock and theoretical peak

The active global target is now 800 MHz / 1.250 ns. The authoritative constraint is:

```text
dc/common_clock_800mhz.tcl
```

Historical 1 GHz reports remain immutable provenance and are not valid 800 MHz signoff.

At 800 MHz:

| Datapath | MAC/cycle | Peak MAC/s | Conventional 2-op peak |
|---|---:|---:|---:|
| BF16 Revision8B-B | 512 | 409.6 GMAC/s | 819.2 GFLOP/s |
| Retained INT8 Gemmini | 2048 | 1.6384 TMAC/s | 3.2768 TOPS |
| Native W4A8 dual-dot candidate | 4096 | 3.2768 TMAC/s | 6.5536 TOPS |

For Qwen2 q1024 BF16, retaining the 300 token/s target at 800 MHz requires approximately 99.207% wall MAC utilization. This is a performance risk, not an operator-coverage failure. For Qwen3.8, 512-MAC BF16 and 2048-MAC W8 configurations cannot reach the existing 300 token/s planning point at 800 MHz; the 4096-MAC candidate requires approximately 56.983% wall utilization.

## Reproducible source gate

Run:

```bash
./scripts/run_three_model_operator_primitives.sh
```

Required outputs:

```text
18 emitted root .sv files
MANIFEST.txt
OPERATOR_COVERAGE.csv
SOURCE_GATE.txt
reports/execution/OPERATOR_PRIMITIVE_COVERAGE_V3.json
```

The emitted files from this command are an elaboration smoke artifact. The local Agent must regenerate and hash the authoritative RTL before RTL simulation and DC.
