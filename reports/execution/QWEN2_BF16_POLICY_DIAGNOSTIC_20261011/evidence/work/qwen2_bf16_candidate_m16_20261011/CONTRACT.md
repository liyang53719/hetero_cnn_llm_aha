# Qwen2 L0 BF16 materialization candidate (software only)

The implemented canonical mixed-precision recipe is **not** the same computation as the pinned Transformers 4.40.1 eager BF16 forward. This candidate changes materialization/rounding boundaries while retaining BF16 Matrix operands, increasing-K FP32 FMA accumulation, existing FP32 bias-add order, the existing 16-part QK reduction, and polynomial exponential. It is not implemented hardware and changes none of the frozen scripts, RTL, or thresholds.

Notation: `R(x)` is BF16 round-to-nearest-even, represented in an FP32 container; `F` denotes a separately rounded FP32 arithmetic operation. BF16 inputs are exact FP32 expansions before an FP32 operation. A model graph identifies exposed tensor dtypes; it does not specify the native BLAS reduction tree or the internal fused Linear bias schedule. Those are not claimed to match the serial hardware schedule bit-for-bit.

| Node | Current canonical/hardware recipe | Pinned official eager BF16 path | Candidate / minimum wiring |
|---|---|---|---|
| Input and weights | BF16 checkpoint values expanded to FP32 containers. | Layer weights and hidden input are BF16. | No Matrix operand-width or weight change. Preserve existing input values. |
| Input RMSNorm / post-attention RMSNorm | FP32 square, serial sum, mean, epsilon, sqrt and reciprocal; `R(F(F(x*inv)*gamma))`. The normalized intermediate remains FP32. | Convert input to FP32; FP32 variance and rsqrt; **cast normalized value back to BF16 before gamma multiplication**, whose output is BF16. | `R(F(R(F(x*inv))*gamma))`. Add RNE at the normalized-value register before the existing gamma product. Keep scalar math/reduction unchanged. |
| Q/K/V, O, gate/up/down Dense | RNE at Matrix A/B ingress; increasing-K BF16×BF16→FP32 FMA; then Q/K/V bias in FP32; store FP32 output. | BF16 Linear inputs/weights/bias, exposed output BF16. Internal native reduction and bias scheduling are not specified by this source. | Preserve full accumulation and current bias-add order, then add RNE only at completed Dense result publication. No intermediate accumulation rounding. |
| RoPE table | Double-libm-generated table stored FP32. | Inverse frequency, position products, cos/sin initially FP32; table cast to query/value dtype, BF16 for this run. | RNE table values at use. M16 rounded table was bit-identical to native. Table generation must be independently checked for larger lengths; no native intermediate is injected. |
| RoPE pair | Two separate FP32 products and FP32 add/sub; FP32 result. | BF16 eager multiply result for each product, then BF16 add result: `R(R(q*c)+R(rotate(q)*s))`. | Add BF16 RNE to both product registers and final pair sum. Keep existing separate arithmetic and half-split indexing. |
| QK dot | BF16 operands; 16 FP32 partial FMA chains followed by ordered FP32 add reduction. Dot remains FP32. | BF16 operands; exposed `matmul` result BF16. Native kernel reduction order is backend-dependent. | Keep existing 16-part FP32 reduction; RNE the completed dot once. |
| QK scaling / masked logits | Multiply FP32 dot by FP32 `1/sqrt(HD)`; store FP32 scores. Hardware visits causal keys only. | Scale the **already BF16** dot, exposed scaled score BF16; mask addition also materializes BF16. | RNE completed dot, retain existing FP32 reciprocal multiply, then RNE scaled score. Causal skipping remains valid. The software observer additionally computes masked-future scores for diagnostics only. |
| Softmax internal | FP32 score difference, polynomial exp7, serial FP32 sum/reciprocal; probability gets BF16 rounded at PV ingress. | Stable softmax explicitly runs FP32 on BF16 logits; result is then cast BF16. | Keep FP32 softmax arithmetic and existing approximation. Capture FP32 softmax separately; BF16 probability at the existing ingress matches its materialized boundary. Do not compare this FP32 internal tensor under an invented BF16 per-element threshold. |
| PV / attention reshape | BF16 probability/V ingress; FP32 FMA accumulation; FP32 published attention. | BF16 probability and V; exposed PV output BF16; reshape is a view/reorder. | Add RNE to completed PV accumulation before publication. Reshape/caches/GQA repeat use the candidate's own values. |
| O projection + first residual | Dense FP32 output; FP32 residual add and FP32 publication. | O result BF16; BF16 + BF16 residual result BF16. | Dense publication RNE as above; add RNE at residual output. |
| FFN SiLU and product | Gate/up Dense FP32 outputs. FP32 stable SiLU via exp7; directly multiply unrounded SiLU by up; store FP32 act. | Gate/up outputs BF16; exposed SiLU output BF16; SiLU×up product BF16; down output BF16. | RNE Dense gate/up outputs; RNE SiLU before up multiplication; RNE product; RNE down output after unchanged Matrix accumulation. |
| Final residual | FP32 residual + FP32 down → FP32. | BF16 residual + BF16 down → BF16. | RNE final residual add. |

## Source evidence

Pinned source: `config/upstream/weight_headers/qwen2_1p5b/modeling_qwen2.py`:

- RMSNorm: lines 85–90, especially normalized `.to(input_dtype)` before gamma.
- RoPE generation/cast: lines 101–126; products and sum: lines 160–164.
- Dense definitions and exposed calls: lines 228–231, 255–257, 313.
- QK matmul then scaling: line 283; mask: line 297; FP32 softmax then dtype cast: line 300; PV: line 302.
- MLP: lines 174–180; residuals: lines 776 and 782.

Current recipe: `chisel/continuous_prefill/tests/qwen2_block.cpp`, lines 112–141. Corresponding hardware evidence in `Qwen2Block.scala`: Matrix BF16 ingress lines 156–178; norm intermediate/publication lines 302–303; Dense bias/publication lines 420–422; RoPE products/sums lines 431–436; QK reduction/scaling lines 447–448; probability/PV lines 455–463; SiLU/product lines 469–474.

## Which numerical gate applies

1. The old `compare_qwen2_stack_reference.py` budget (relative L2 ≤ 0.01, cosine ≥ 0.9999, normalized max ≤ 0.05) is explicitly a **developer-defined final-output bring-up budget**, not model quality or a native BF16 operator contract (lines 22–26). Its reference deliberately creates FP32 checkpoint tensors and computes FP32 equations (lines 49–79). It is appropriate as the saved mixed-recipe-versus-FP32 diagnostic. It cannot decide whether an implementation matches native BF16: the official BF16 and official FP32 paths themselves differ materially. The saved failures remain failures of that diagnostic; none are erased or reclassified as passes.
2. `spec/numerical_contract.md` lines 15–18 retain BF16 Matrix / FP32 accumulation; lines 23–29 give BF16 operator max/mean ≤ 0.03125/0.005 and block ≤ 0.05/0.01. Line 36 forbids hiding an operator failure behind a passing final output. The candidate is evaluated per materialized BF16 node against the pinned official BF16 execution, with final `y` using the block gate. Mask/storage/view semantics remain exact checks.
3. The official BF16 path's **internal FP32 softmax** is a separate tensor from its **BF16 probability**. We report its actual error against that internal FP32 tensor without inventing a per-element tolerance. Existing row-sum error ≤ 2e-5 and exact causal semantics are checked; BF16 `prob` separately uses the BF16 operator gate.
4. There is a contract-text mismatch to resolve explicitly before hardware acceptance: numerical_contract v0 line 18 describes FP32 pair rotation followed by BF16 output rounding; the fixed eager native BF16 source rounds both products before the final sum. This candidate follows the requested fixed official materialization for diagnosis. It does not silently edit v0 or claim the two RoPE equations are identical. Selecting that node reference for the eventual hardware gate needs an explicit architecture-contract clarification; no threshold relaxation is proposed.

## Small-run result and scope

M16 candidate completed in 3.711 seconds. All 15 principal stages plus scores, logits, BF16 probability and SiLU met the unchanged BF16 gates against both native and independently evaluated BF16 paths. Native final `y`: max absolute error 0.00390625, mean 1.98893e-5, relative L2 0.000580228 (old mixed recipe 0.120399 against native BF16). Native M16 scores/logits were bit-identical. FP32 internal softmax max error was 2.08616e-7; this is a diagnostic value, not a new acceptance threshold. Cos/sin BF16 tables were bit-identical.

The candidate CPP, exact edit list, compiler flags, binary hashes, all outputs and comparisons are retained next to this document. No claim of area, timing, hardware cycles, physical utilization, RTL correctness, or larger-input acceptance follows from this small software run.

## Complete coverage and larger candidate outcome

M16 was subsequently checked from its saved candidate outputs with all 29 observer nodes, including nine nodes derived only from the candidate's own outputs or immutable inputs/constants (`x`, cos/sin, mask, caches, repeated KV, PV view). No new C++ execution was needed. All 12 exact/normative semantic checks passed; maximum FP32 softmax row-sum error was 1.78814e-7. `FULL_NODE_CHECK.json` contains the full evidence; the original 20-node `RESULT.json` is retained unchanged.

M128 then used exactly the same candidate C++ and ELF, with the original 128-token readonly arena, completing in 30.028 seconds. All 29 nodes and the same semantic checks were recorded. The final native-BF16 error improved to max 0.03125, mean 2.13437e-5, relative L2 0.000748274; all 15 principal stage gates passed. **The complete gate still fails:** scores max error 16 at `[batch=0,head=6,query=70,key=75]`, and logits max error 8 at `[0,9,102,2]`. The first point is masked future; the second is causally visible. Per-node failure remains binding even though final output passes. FP32 softmax row-sum error was 7.15256e-7; all twelve semantic checks passed. The independent BF16 comparison separately fails gate, logits, probability, and scores and is also preserved.

## Remaining reduction issue: no justified one-point fix

- Masked future QK `[h6,q70,k75]` has identical candidate/native Q and K. Current 16-part and tested 1/2/4-part cyclic/contiguous FP32 schedules all produce scaled BF16 2560, while the native backend produces 2576. A diagnostic mathematical sum is 28992.000022888184, just above a BF16 midpoint; an intervening FP32 rounding loses that sign. That explains sensitivity, not which instruction/kernel native used. No FP64 result is used in candidate arithmetic.
- Visible logits `[h9,q102,k2]` first diverges in Q projection `[token102,column1215]`. Its n0 row is bit-identical. Candidate/native BF16 Q are 1.8515625/1.84375; K channel 63 is 430. The serial-FMA, then-bias FP32 result is 1.8476572036743164, above midpoint 1.84765625. Initializing bias in the accumulator, or certain multi-part sums, changes the side here, but causes regressions at other tested points. Native output cannot be globally reconstructed by selecting the order that happens to fix these two coordinates.
- Seven Dense coordinates and three QK coordinates were probed without a full model rerun. Some native results differ from every tested serial/2/4/16-part variant. The current evidence does not establish the native bias or reduction implementation.

The saved build reports MKL, MKL-DNN 3.7.1 and AVX512 capability. It does **not** prove the kernel selected for the original full-shape BF16 Linear/QK calls, their block-K schedule, whether bias is an initial accumulator/fused post-op, or executed instructions. A defensible next step is to observe and pin those actual backend rules, then model one uniform resource-compatible FP32 accumulation/bias schedule and regress broadly. Matrix precision, thresholds and lane counts must not be altered to fit individual coordinates. The RoPE specification mismatch described above remains a separate contract decision.

## Bounded backend observation (two operators, exact full-output reproduction)

A subsequent observation reran only the original-shape M128 Q Linear and QK matmul/scaling under the original torch 2.10.0+cpu, Transformers 4.40.1, four-thread eager configuration. The complete BF16 QR and scaled-score output bytes matched the saved official nodes exactly. Profiler/oneDNN verbose confirmed:

- Q Linear: `aten::linear → aten::addmm`, oneDNN `brg_matmul:avx512_core_bf16`, `128x1536:1536x1536`, BF16 source/weights/destination, `attr-post-ops:sum`.
- QK: `aten::matmul → aten::bmm`, oneDNN `brg_matmul:avx512_core_bf16`, `12x128x128:12x128x128`, BF16 source/weights/destination, no sum post-op.

This establishes the dispatch/kernel family for the reproduced operators. It does not establish instruction-level accumulation, block-K merge order, or precise internal rounding/bias order. The original runner did not save raw unscaled dots or original strides; strides were reconstructed from source views/transposes/repeat_kv and complete scaled output was checked. Trace, verbose output, shapes/strides, CPU information and output hashes are in `../qwen2_native_backend_observation_20261011/`.

## Minimal hardware connection caveat

Keep FP32 arena containers and existing transaction byte counts. The existing `ElementwiseMemoryEngine.dstBf16` flag is a packed-storage selection, not merely an arithmetic-rounding flag: it changes output stride, byte count, address shift and packet packing. It cannot be switched on to implement these residual RNE boundaries without changing the layout contract. A later implementation needs BF16 RNE followed by FP32-container expansion in the existing result/write path, or a separately specified rounding-in-FP32-container option. Source: `ElementwiseMemoryEngine.scala` lines 60–63 and 130–146. Dense/attention publication similarly must round only completed results, never partial accumulators or a Q/K/V Dense value before its existing separate Bias command in owner-driven operation.

## Conditional QK separation on the candidate's own operands

A final bounded diagnostic called only the same original-shape native BF16 QK matmul and scaling with the candidate's own saved M128 Q/K. The full input artifacts were rebound to the original candidate ELF outputs and immutable recipe arena first. Of 99,072 causally visible score elements, all were bit-identical to the candidate. Four masked-future elements differed, with maximum 16 at `[0,6,70,75]`. Thus the valid logits divergence in this observed input is upstream of QK, while a separate masked-future QK arithmetic divergence remains real.

Compared with the pure official inputs, this conditional call still differed in 11 active scores (maximum 8 at `[0,9,102,2]`) and one masked-future score. At the active maximum, conditional/candidate were both -848 and official was -856. This isolates operand propagation for this input; it neither proves a universal reduction rule nor changes any original full-chain gate. The call took 1.09 ms. Exact source, actual-input identities, shapes, settings and full-output hash are saved in `../qwen2_candidate_conditional_qk_20261011/RESULT.json`.
