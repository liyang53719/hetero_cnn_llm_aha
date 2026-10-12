# Conditional full-L3 Matrix utilization bound

Read-only source/count audit, 2026-10-12. No model, build, test, RTL, or network execution. Arithmetic and source-file SHA-256 checks only.

## Verdict

The proposed bound is valid **conditional on executing these same scalar recipes literally through one existing BlockScalarFloat, with a fixed 4096-MAC/cycle Matrix denominator**. It is not measured utilization, a latency prediction, hardware verification of C2/M128 integration, or a universal architecture ceiling.

Each window has 128 new tokens. The prior C1 receipt counts 2,566,144 scalar requests once. Current C2 changes each of the (8+2)*128=1280 normalized heads by +30 Add, -6 Mul, +1 Sqrt, +1 Div: +26 requests/head, +33,280/window.

| Policy | Add | Mul | MulIeeeRne | Div | Sqrt | Total requests N | Conservative wall-cycle floor 3N |
|---|---:|---:|---:|---:|---:|---:|---:|
| C1 prior receipt | 1,016,704 | 1,155,840 | 393,344 | 128 | 128 | 2,566,144 | 7,698,432 |
| C2 source-derived | 1,055,104 | 1,148,160 | 393,344 | 1,408 | 1,408 | 2,599,424 | 7,798,272 |

Dense Matrix work is 128*(1024*4096 + 2*1024*512 + 2048*1024 + 3*1024*3584) = 2,348,810,240 MAC. The 4096-wide q projection includes query plus attention gate exactly once; the 3584-wide MLP gate/up/down are three distinct projections. QK/PV adds 2*8*128*keys*256 = 67,108,864 MAC for cold keys=128, or 134,217,728 for carried keys=256. No old-window projection is repeated in the carried numerator.

| Policy | Cold full-L3 logical MAC | Carried full-L3 logical MAC | Cold upper bound | Carried upper bound |
|---|---:|---:|---:|---:|
| C1 | 2,415,919,104 | 2,483,027,968 | 7.6616121309% | 7.8744346901% |
| C2 | 2,415,919,104 | 2,483,027,968 | 7.5635217648% | 7.7736195916% |

Formula: U <= full-L3 logical Matrix MAC / (4096 * 3N). Matrix overlap cannot evade a one-service throughput floor. Do not add Matrix issue cycles to this scalar floor if overlap is allowed. Omitted memory, Matrix drain/feedback, softmax, output gating, post-attention RMS, residual, FFN nonlinearity, command, and ACK work can only increase full-job wall time under the mapping assumptions. Scalar arithmetic is not Matrix MAC work.

## Proof and source locations

- `BlockFloat.scala:29-30,39,55-81,83-89,108`: one in-flight operation; request ready only in idle, result valid only in done. For successful finite Add/Mul/MulIeeeRne, accepted request at E0, arithmetic at E1, result accepted E2, next request E3: minimum acceptance II=3. Div/Sqrt must additionally visit divIssue and divWait; they cannot improve this lower bound. Reject/early-error paths are excluded by successful-execution scope.
- Endpoint precision: II alone gives first scalar request to final scalar result >=3N-1, not exactly 3N. A complete launch includes input reads and final write ACKs. Independently, the 256 (C1) or 2816 (C2) Div/Sqrt operations must each traverse an extra state, so even their conservative mandatory overhead more than covers the one-cycle endpoint difference. Thus the stated full-job floor 3N is safe; it is not an equality or a measured cycle count.
- `Qwen2Block.scala:95-109`: one BlockScalarFloat; external requests retain it until their result is consumed. `QwenOwnerProtocol.scala:270-281`: RMS, Q/K Norm, RoPE and other clients explicitly multiplex onto that one existing core scalar service and the accepted owner retains exclusive access. `MatrixPipeline.scala:35,61,78-80,99`: eight 512-MAC slices, fixed physical total 4096, including idle or clock-gated periods in the denominator.
- `norm_rope/coordinator.py:99-113,144,347-355`: same scalar instance is required for RMS, Norm and RoPE; the aggregate count is `scalar.calls - baseline`, summed once. Do not also add nested per-command/per-owner counters. `norm_rope/scalar.py:25-45` and `qwen35_gdn_prefill/rms_owner.py:124-149`: each public scalar call increments exactly one operation counter under exclusive ownership.
- `norm_rope/owner.py:437-488`: C2 reduction uses 256 inner adds +24 residue combines +8 lane combines =288 versus C1's 16*(15+1)=256; C2 removes the C1 reciprocal approximation's 2 adds and 6 multiplies and adds one Sqrt/Div pair. Net +30/-6/+1/+1 =26. Shared output work at lines 498-502 is unchanged. Per normalized head C1=515 Add+775 Mul=1290; C2=545 Add+769 Mul+1 Sqrt+1 Div=1316.
- `norm_rope/owner.py:532-543`: each RoPE head has 32*(4 Mul+2 Add)=192 calls. Across 1280 heads: 245,760. Input RMS receipt/source contributes 669,184; C1 Norm contributes 1,651,200; these sum to 2,566,144. Vector Add calls/lanes and Matrix executed FMAs are separate resources and are not added to scalar requests.
- `config/upstream/qwen3_5_0p8b/config.json:14-18,19-23,55-57`: layer 3 full attention, H=1024, head dimension 256, 8 Q heads, 2 KV heads, FFN width 3584. `modeling_qwen3_5.py:751-761,777-784,820-826` and `layer3_payload_pin.json:21-57,84-145` verify all seven projection dimensions. `layer3_bf16_contract.json:8-17` fixes layer 3, batch 1, 128 query tokens, cold/past128 cases and eager backend.
- `modeling_qwen3_5.py:724-733`: QK and PV use all 8 query heads after KV broadcast. This is the repository's rectangular logical-MAC convention, including masked/zero terms, not a count of causal nonzero terms: `QwenOwnerProtocol.scala:118` sets `(m*cacheLength)<<12`; lines 263-265 explicitly include causal-zero PV products. A stricter causal-useful numerator would make the bound tighter.
- Baseline receipt `work/l3_norm_rope_actual_20261012/actual_m128_02/summary.json:185134-185141,199372-199379` records the same C1 counts separately for cold and carried windows. It reports prefix-only success, not full-block execution; hardware cycles and hardware utilization are null. Software ticks and 671,088,640 executed prefix FMAs are not full-L3 wall cycles or full-L3 useful MAC.

## Limits that must accompany the result

The Python scalar calls execute synchronously between memory-handshake ticks. `norm_rope/owner.py:1-7` explicitly disclaims scalar timing; `norm_rope/coordinator.py:364-367` disclaims Chisel/RTL/full-block/KV-cache execution. C2 is source-derived and not implemented by the production Chisel owner: `owner.py:45-54` reports that fact, while `QkNorm256Owner.scala:194-196` accepts only C1. The current production owner integration also instantiates input RMS with maxTokens=1 (`QwenOwnerProtocol.scala:80`); this is not evidence of a built M128 full-L3 path.

All counted requests serialize only under the stated one-to-one mapping, without removing repeated zero adds or gamma additions, replacing reductions, vectorizing, fusing operations, adding scalar instances, or precomputing work outside the measured interval. The scalar ownership/model identities support that mapping; they do not prove a future hardware implementation must preserve it. A different mapping needs a fresh count/resource audit.

## SHA-256 pins observed during this audit

Paths below are relative to the repository root. Current C2 owner/coordinator differ intentionally from the historical C1 receipt snapshots; do not claim their hashes match the old run.

| File | SHA-256 |
|---|---|
| chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BlockFloat.scala | 9863718ca90089bf812eb07dbd82ce16d982a8c74b04d7543de1bd2dfb1e37b5 |
| chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala | 1152cb11e145c27f271b0170913194bd66ce2930008a75e3a580d5660e410a43 |
| chisel/continuous_prefill/src/main/scala/heteronpu/continuous/QwenOwnerProtocol.scala | c8d6cfd95901bc9f2cae3f248d542cb532b1b66aec1be98942a9a7533d3ca542 |
| chisel/continuous_prefill/src/main/scala/heteronpu/continuous/MatrixPipeline.scala | dd1f3859ac65fa4d4839105cf166cb5d3a1f4d2d786991eb0f22749ad4ceca3d |
| chisel/continuous_prefill/src/main/scala/heteronpu/continuous/QkNorm256Owner.scala | c12183ddb29ab3ce66dc59083524c204f55554757218ced438c8f8ae4c7d60b6 |
| chisel/continuous_prefill/src/main/scala/heteronpu/continuous/PartialRope64Owner.scala | 7a3f5bffe06772671f30ac1484065afae9abc895063a2e4769999bf76487c322 |
| candidates/qwen35_attention_prefill/norm_rope/scalar.py | 115dc84f5ac8786e59ba542466e21f8a97003726365a7ba7743fc6c143f433d5 |
| candidates/qwen35_attention_prefill/norm_rope/owner.py | ca413aaab8b231e86027b9ff9b570809e90513eb798c362ce90957f29792c8ab |
| candidates/qwen35_attention_prefill/norm_rope/coordinator.py | b4e85952f4802d7a780c0fbe799baf8298fc014109de99de691219f797ff5f09 |
| candidates/qwen35_gdn_prefill/rms_owner.py | 99e554de800bd876bb4ef772aca049d1678bfcbab9d0ec018d10c868b7bbee96 |
| config/upstream/qwen3_5_0p8b/config.json | b90b86f35c8e6925ef74ee04d0e758f0a845c83a42089ad82bbaa948de9b4204 |
| config/upstream/qwen3_5_0p8b/modeling_qwen3_5.py | aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18 |
| config/upstream/qwen3_5_0p8b/layer3_bf16_contract.json | 13b52da81746346f62c6a2f28cc1d6fa565989bd71d834dd4951ee2056355d97 |
| config/upstream/qwen3_5_0p8b/layer3_payload_pin.json | ab9735a92f3b3377737288621019bccd855a5696bd4d02b2d8257cbf24a5b0ac |
| work/l3_norm_rope_actual_20261012/actual_m128_02/summary.json | 3d60e35d0278fc1c09a902929949d24415e7fcfad842cb2b8c120cc52c1c3f02 |
