# Numerical contract v0

This contract is frozen before upstream RTL integration. Threshold changes require a versioned architecture decision and a before/after regression; they must not be changed merely to make a failing implementation pass.

## Integer paths

- INT8 GEMM/Conv: signed two's-complement operands, INT32 accumulation, bit exact.
- Signed INT4: values `[-8, 7]`, low nibble first in packed bytes.
- W4 grouped quantization: groups along K, group size 64 or 128, symmetric per-group/per-output-channel scale, `scale=max(abs(w))/7` with zero groups using scale 1.
- W4-storage/W8-compute: unpack/convert before the INT8 array; accumulation remains INT32.
- Requantization: rounding and saturation mode must be descriptor-controlled and bit exact against the software golden.

## BF16 paths

- BF16 conversion: round-to-nearest-even; payload is compared after clearing the low 16 FP32 bits.
- BF16 Matrix operands, FP32 accumulation.
- RMSNorm/LayerNorm reduction, online-softmax M/L/O and Attention output accumulation use FP32.
- RoPE tables/operands may be BF16, but pair rotation reference is FP32 followed by BF16 output rounding.

Initial block-level thresholds for target-shape RTL co-simulation:

```text
BF16 single operator:
  max_abs <= 3.125e-2
  mean_abs <= 5.0e-3

BF16 one Transformer block:
  max_abs <= 5.0e-2
  mean_abs <= 1.0e-2

INT8 KV one Transformer block:
  max_abs <= 5.0e-2
  mean_abs <= 1.0e-2
```

A pass also requires no NaN/Inf and no hidden tensor with error above its operator threshold. End-to-end thresholds do not override per-node failures.

## Softmax

- Dense and blockwise online implementations compare in FP32.
- Probability sum absolute error <= `2e-5` per row in the functional model.
- Causal/mask semantics must be exact.
- Hardware approximation error for exp2/reciprocal is measured separately from scheduling/data movement error.

## KV cache

- BF16 storage: readback must equal the BF16-rounded append value exactly.
- INT8 storage: per-token-head symmetric scale; no cross-token scale sharing in v0.
- Page allocation and address translation are exact and independent of numerical tolerance.
- Prefix sharing/COW tests require source tensors to remain bit-identical after destination writes.
