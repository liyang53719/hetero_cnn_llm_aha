# Experimental BF16 Attention block v3

This is an explicit, default-off `bf16AttentionBlock` profile for Qwen3.5-0.8B layer 3. It requires the existing Attention-core, QKV and QK Norm/RoPE profiles. The admitted execution geometry is **M1 only**: typed activation rows=1, tokenBase=0, tokenCount=1. A source row may be extracted from an official cold128 capture, but that does not constitute M128 block execution. Normal launches retain one cache checkpoint; reset invalidates it and no restore protocol exists.

The profile uses the standard 128-bit command, its three descriptor roots A/B/D, and existing public record types. It introduces no opcode, owner kind, tensor format, resource, or private SRAM address. Existing QKV v2, QK Norm/RoPE v1, Attention-core v2 and GDN profiles retain their previous contracts.

## Public wire extension

New surrounding commands use `ATTENTION_POLICY=0x24`, version 3, followed by the unchanged terminal `ATTENTION_CONTEXT=0x26`, version 2. Existing QKV, Norm/RoPE, append and QK/softmax/PV records are byte-for-byte their existing versions. The former core fence is absent in a full-block stream.

| Field | 72-bit payload coordinates | Complete 128-bit record coordinates | Required value |
|---|---|---|---|
| version | 7:0 | 63:56 | 3 |
| operation | 11:8 | 67:64 | 4 fence, 5 RMS, 6 Dense, 7 elementwise |
| tokenBase | 43:12 | 99:68 | 0 |
| tokenCount | 51:44 | 107:100 | 1 |
| recipe | 59:52 | 115:108 | 0; numerical behavior fixed by v3 operation/role |
| role | 62:60 | 118:116 | Enumerated below |
| reserved | 71:63 | 127:119 | 0 |

Common descriptor subtype/flags are zero. A tensor prefix is native contiguous BF16 `TENSOR_BASE -> SHAPE4 -> STRIDE3`; element strides and all trailing shape dimensions are checked. A continues through its program, policy and context; B/D terminate after STRIDE3. New Dense uses `MATRIX_GEMM/Engine.MATRIX`, `MATRIX_OP -> MATRIX_AUX -> ATTENTION_POLICY -> ATTENTION_CONTEXT`. Its MATRIX_AUX payload is `0x004000040020ffffff`. New SFU operations use `SFU_VECTOR/Engine.SFU_CGRA`, `SFU_PROGRAM -> ATTENTION_POLICY -> ATTENTION_CONTEXT`. SFU_PROGRAM has program_id=0x30, two inputs, one output, BF16 input/output, 16-bit lanes, vector_lanes=0 and flags=0. No fourth root is added for new commands; the existing Q Norm gate auxiliary root is retained unchanged.

RMS roles 0/1 mean input/post-attention RMS1024. Dense roles 0/1/2/3 mean O, FFN gate, FFN up and down. Elementwise roles 0/1/2/3 mean sigmoid gate multiplication, first residual, SiLU-times-up and second residual. Fence has role zero. The existing owner kinds are Dense=1, RmsNorm=11 and Elementwise=13; elementwise job operations are respectively 2,0,1,0. Kernel integration must explicitly enable the default-off SigmoidMul=2 owner extension.

## The 22 commands

| PC | Operation | Input roles | Output role | Records | A record index |
|---|---|---|---|---:|---:|
| 0 | input RMS | raw hidden, input gamma | input_norm | 12 | 0 |
| 1 | Q projection | input_norm, Wq | q | 21 | 12 |
| 2 | K projection | input_norm, Wk | k | 21 | 33 |
| 3 | V projection | input_norm, Wv | v | 21 | 54 |
| 4 | Q Norm256 | q, gammaQ | norm_q and Q gate | 15 | 75 |
| 5 | K Norm256 | k, gammaK | norm_k | 12 | 90 |
| 6 | Q partial64 RoPE | norm_q, trig | rope_q | 12 | 102 |
| 7 | K partial64 RoPE | norm_k, trig | rope_k | 12 | 114 |
| 8 | KV append | rope_k, v | staging cache tail | 11 | 126 |
| 9 | QK | rope_q, cache | internal scores | 13 | 137 |
| 10 | softmax | internal scores, NULL | internal probabilities | 9 | 150 |
| 11 | PV | probabilities, cache | context | 13 | 159 |
| 12 | sigmoid multiply | actual Q gate, context | sigmoid_mul | 12 | 172 |
| 13 | O projection | sigmoid_mul, Wo | o | 13 | 184 |
| 14 | residual add | raw hidden, o | residual1 | 12 | 197 |
| 15 | post RMS | residual1, post gamma | post_norm | 12 | 209 |
| 16 | FFN gate | post_norm, Wgate | ffn_gate | 13 | 221 |
| 17 | FFN up | post_norm, Wup | ffn_up | 13 | 234 |
| 18 | SiLU multiply | ffn_gate, ffn_up | silu_mul | 12 | 247 |
| 19 | down projection | silu_mul, Wdown | down | 13 | 259 |
| 20 | residual add | residual1, down | residual2 | 12 | 272 |
| 21 | full-block fence | cache, raw hidden | residual2 | 12 | 284 |

The canonical serializer emits 296 distinct descriptor records and sequential events 0 through 22. There are 19 owner jobs: QK/softmax/PV are one validated, fused owner, while the terminal fence has no owner job. Its three completions remain delayed until the actual PV ACK.

H=1024, raw Q projection=4096, Q/content/gate/context=2048, K/V=512 and FFN=3584. Q projection remains per-head `[content256,gate256]`; Q Norm creates the separate contiguous gate. O weights have shape [2048,1024], and down weights [3584,1024]. RMS1024 uses FP32 `1 + raw BF16 weight`, then the existing RMS numerical recipe. SigmoidMul requires A=actual Q gate and B=actual context; it computes BF16(sigmoid(A)) followed by BF16(sigmoid(A)*B). Reversed roots are rejected before owner issue. Sigmoid multiplication preserves BF16 sigmoid rounding before BF16 context multiplication; SiLU multiplication preserves the existing BF16 SiLU boundary before multiplying up. This contract does not replace the independent numerical reference.

## Producer, allocation and checkpoint rules

The frontend binds actual acknowledged typed allocations for every intermediate. Readonly preloaded lookalikes cannot satisfy input RMS, Q gate, context, O, either residual or FFN dependencies. Raw hidden retains source role zero and is consumed unchanged by the first residual. New O/FFN Dense ACKs cannot update the Q/K/V producer slots.

All declared physical allocations include the 64-byte padded final burst. Distinct source roles, parameter roles, outputs, virtual score/probability reservations and cache allocations cannot overlap. Score/probability rectangles reserve logical BF16 allocations but remain owner-internal and do not imply DDR materialization. The sole cache alias exception is exact reuse of the committed cache allocation by append at its uncommitted tail.

The twelve persistent parameter identities, in order, are Wq, Wk, Wv, gammaQ, gammaK, trig, input gamma, Wo, post gamma, Wgate, Wup and Wdown. Identity includes full address/rank/dtype/dimensions/payload/padded extent. The raw hidden changes per launch. Carried launch length/generation and RoPE absolute query position must match the last committed checkpoint. The same complete trig allocation is retained across positions.

Append ACK stages new cache length; PV ACK stages its context. Every downstream ACK publishes only a transaction-local producer. Acceptance of completion 22, after the exact second-residual ACK and all producer checks, atomically commits cache allocation, new cache length, next generation, **final residual allocation** and all twelve parameter identities. No earlier core fence is accepted. Holding completion 22 ready low must hold the committed checkpoint unchanged.

On a downstream error, already written cache-tail bytes remain staging; committed length/generation, old final output and parameter identities do not advance. The existing fail-stop frontend requires reset after a poisoned error; this is not rollback, recovery or reset restoration. Between successfully committed launches, expired scratch can be reused, including old context, while the cache, latest final output and all parameters remain protected.

## Software and evidence boundary

`host_bf16_attention_block_descriptor.py` provides typed v3 construction/parsing, full-stream producer/allocation validation and carried-checkpoint preflight. Validation never asserts that an owner actually ran or that a prior fence committed. The caller of carried validation must establish the real preceding committed stream.

Python tests exercise wire roundtrip, record inventory, full source binding, malformed fields/strides/events, alias rejection and checkpoint lifetime. `HostAttentionBlockCommandsSpec` is explicitly CONTROL_ONLY and mocks owner receipts; it checks cold/carried launches, held fence, failure at PC20, readonly-input substitution, reversed sigmoid-root rejection and default-off core behavior. Neither suite establishes full-block numerical execution, M128 execution, reset restoration, physical-resource counts or QoR. Those remain separate integration gates.
