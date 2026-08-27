# Qwen3.8-Flash-Next executable text E0

## Purpose

This gate converts Qwen3.8 support from descriptor-only inventory into a
stateful, executable architectural reference that can be used to derive RTL
tests and official-weight traces.

## Executed path

```text
token embedding -> 4 residual branches
  -> optional PLE hash/lookup/projection/gate/dilated-conv
  -> Gated Residual attention read
  -> GDN recurrent layer OR QSA sparse-attention layer
  -> Gated Residual attention write
  -> Gated Residual MoE read
  -> top-k routed experts + gated shared expert
  -> Gated Residual MoE write
  -> final hyper-merge RMSNorm
```

The reduced model uses four layers with the same repeating structural pattern as
the official model. All convolution, recurrent, index-key, KV, PLE and residual
states persist across token steps. Running the same token sequence through the
`run()` prefill entry and repeated `step()` decode entry produces exactly the
same outputs and state.

## Evidence

- `src/heteronpu/qwen38_runtime.py`: integrated executable text model.
- `src/heteronpu/qwen38_schedule.py`: 48-layer hardware micro-op ownership.
- `src/heteronpu/gated_deltanet.py`: recurrent and independent chunk algorithms.
- `src/heteronpu/moe_router.py`: router plus routed/shared expert execution.
- `src/heteronpu/mtp.py`: speculative state transaction.
- `tests/test_qwen38_runtime_e0.py`: state, prefill/decode, chunk, QSA, MoE,
  schedule and frozen-hash gates.
- `reports/execution/qwen38_text_e0_result.json`: deterministic execution trace.
- `reports/execution/gdn_chunk_e0_result.json`: 100 randomized chunk/recurrent
  comparisons.
- `config/qwen38_tiny_e0_contract.json`: immutable tiny-model hashes.

## Hardware mapping

| E0 operation | Primary owner |
|---|---|
| GR low-rank read and projections | Matrix + SFU |
| GR injection write | SFU/vector |
| PLE hash and token context | State/control |
| PLE embedding fetch | host/DDR + DMA/cache |
| PLE key/value projections | Matrix |
| PLE signed-sqrt gate and dilated conv | SFU/state sidecar |
| GDN projections and state outer products | Matrix/state engine |
| GDN decay, beta, L2Norm and gated norm | SFU |
| QSA index projection | Matrix |
| QSA pool/ReLU/reduce/top-k | SFU/index engine |
| Sparse KV gather | KV engine |
| Sparse QK/online Softmax/PV | Matrix + SFU |
| MoE router/top-k | Matrix + SFU |
| Expert gate/up/down | Matrix weight-cache path |
| Shared expert gate | SFU |
| MTP verify/rollback | control + state engine |

## Claim boundary

This closes E0 only. The next evidence must come from the local Agent:

1. official-weight node traces;
2. E1 RTL for each stateful backend;
3. E2 one-block/four-layer comparisons;
4. E3 integrated scheduling and bandwidth;
5. E4 timing, area and power.
