# Continuous Qwen2 block/stack numerical contract

## Scope

This contract covers the Chisel `Qwen2ContinuousBlock` and `Qwen2LayerStack` functional implementation, not a claim that the production 512-MAC/Command128/pinned-iDMA system or a complete model is finished. `Qwen2LayerStack` currently instantiates the standalone block. The retained array adapter must be validated separately; physical connection to 512 lanes is not proof of 512 useful MACs per cycle.

Hardware modifications belong in Scala/Chisel. Generated SystemVerilog is an output. The C++ harness generators transform test code only; they must never modify generated or retained production RTL.

## Actual data continuity

Only initial hidden, weights and RoPE tables are loaded before launch. Hidden B and scratch are NaN-poisoned. A memory write becomes visible at its successful response handshake. The child block publishes its final completion only after its final output write; the layer controller checks status, phase 14 and epoch before publishing the destination hidden arena. The next layer consumes that arena, never an oracle tensor.

Layer weights occupy distinct physical ranges. Hidden A/B alternate; scratch and the read-only RoPE table are reused. The layer-controller admission check rejects range overlap, insufficient weight stride, bounds overflow, zero/oversized dimensions and epoch wrap. Runtime failures do not publish an output version and require reset before another request.

An oracle may use earlier oracle results to compute later oracle results, but those results are never written into DUT memory. Its only role is comparison.

## Shape and execution gates

Real shape is H=1536, F=8960, Q heads=12, KV heads=2, head dimension=128. Runtime token count is explicit and must not exceed 1024. Tiny shape H=64/F=128 is a functional graph test, not a real-size model result.

Per layer the harness checks 15 phases. Expected checked FP32 values are 41,472 per token for the real shape and 1,056 for tiny. Every checked element must be bit-exact against the independent hardware-recipe oracle. A full real-size single-layer 16-token run therefore requires 663,552 checked values; a real-size two-layer one-token run requires 82,944; tiny four-layer 17-token requires 71,808. These are acceptance counts, not statements that any particular run passed.

The completion must report `host_intermediate_writes=0`, no numerical mismatches and positive previous-layer consumption for a multilayer run. All 15 phase commits per layer must occur in order. A PASS line alone is insufficient without the runner exit code, source identities and immutable output hashes.

## Device numerical recipe

* Checkpoint tensor values are expanded to FP32 containers without inventing precision not present in the source.
* Matrix operands use BF16 round-to-nearest-even at the explicitly implemented ingress. Accumulation uses FP32 FMA in the committed K order. No partial-K BF16 rounding or arbitrary reassociation is permitted.
* Layer residual tensors remain FP32. Bias, RoPE, normalization and nonlinear operations follow the committed Chisel operation order and the separately implemented scalar oracle. Their exact approximation coefficients and rounding points are identified by the source manifest, not a generic label such as "FP32 compatible".
* IEEE NaN/Inf in user inputs or produced hidden values is an error. Poison values are not legal replacement inputs.
* Hardware-recipe bit parity is distinct from the checkpoint FP32 equation comparison and from an official Transformers forward. They must have separate receipts.

## Official Safetensors conversion

`pack_qwen2_stack.py` accepts BF16/F16/F32 Safetensors, validates exact Qwen2-1.5B shapes/configuration and writes bounded-memory physical arenas. Matrix tensors are converted from source [N,K] to device [K,N]. Q/K output rows and their bias use an explicit within-head split-half-to-adjacent permutation. V and O weights are not given this permutation. The generated RoPE table and weight/bias transformation must be used together.

The packer stores original shard/config/token hashes and the caller-provided upstream revision. A revision string alone is not authentication that bytes came from the official repository; the receipt records this limitation. Source provenance must also be verified at acquisition. Packing success is `PACKED_NOT_RTL_VALIDATED`.

The current stack packer deliberately does not guess GGUF Q/K layout or quantization semantics. A GGUF extension is developer work and must establish converter revision, quantization decode parity and Q/K coordinate convention before enabling that input path.

## Reference distinction

1. `PASS_PACKED_CHECKPOINT_HARDWARE_RECIPE`: the real DUT consumed packed inputs and matched the hardware-recipe oracle, with poisoned intermediates and actual memory continuity.
2. `PASS_CHECKPOINT_FP32_EQUATION_BUDGET`: actual DUT hidden was separately compared with FP32 equations using the same checkpoint bytes and tokens. Current developer-defined bring-up budget: relative-L2 <= 0.01, cosine >= 0.9999, normalized max-abs <= 0.05. These thresholds are not an established model-quality guarantee.
3. Official framework forward, final logits and complete model quality remain separate gates. Neither of the first two labels implies the third.

Threshold failure requires developer diagnosis. The execution agent must not change tolerances, reset semantics, tested dimensions or expected counts.

## Performance and physical scope

Frequency target is 800 MHz / 1.250 ns. Functional simulation success does not establish this frequency. Do not apply the canonical 512-MAC denominator to the standalone 16-useful-lane functional path. Do not call a direct AXI adapter "pinned iDMA". No per-layer or per-job cycle addition may be presented as a measured continuous full-model request.
