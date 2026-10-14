# M128 bounded execution and separate posthoc result

## Outcome and scope

The fresh same-live pc0..12 software DUT/model execution completed and sealed its output, then its entry process **FAILED** during reference-runtime admission. Its original receipt remains FAILED, acceptance_sealed=false. A separately authorized, read-only posthoc comparison of those exact sealed bytes **PASSed the unchanged BF16 operator contract**. This is not whole-block acceptance and not overall bit-exact equivalence.

- Original execution receipt: `work/qwen2_live_attention_numeric_m128_bounded_20261014/m128_pv32_bounded_actual_v2/RESULT.json`; SHA-256 `38b59e30edcf655300ce3b7c5342809641589edc327482e4ae781e959c04947e`.
- Separate posthoc receipt: `work/qwen2_live_attention_numeric_m128_bounded_20261014/posthoc_v2_compare_v1/RESULT.json`; SHA-256 `ab71f006a03cafea1fda7db66b7be6b437517b25ac24c4c20777e08556a19e44`.
- Final independent review: `work/qwen2_live_attention_numeric_m128_bounded_review_20261014/POSTHOC_RESULT_INDEPENDENT_REVIEW.json`; SHA-256 `cb6ca18d9497e645a0e62cf4aa43e5155bff4bff050178eae00856a6d1b120b0`; status `ACCEPT_POSTHOC_RESULT_WITH_ORIGINAL_RUN_FAILED`.
- pc12 public completion held; 11 owner requests/results, 12 consumed public completions; att ACKed 786432 bytes and terminal but unpublished; all backend debts zero. No finalfence, block-terminal, fullblock pass, RTL, EDA, hardware cycles, or measured hardware busy fraction.
- All 178/185/191 frozen-source closures and all original 77 execution files retained unchanged. No DUT rerun occurred for posthoc. No saved QKV served as a new model input. Exact-copy KV and PV-to-token layout were verified.

## Preserved attempts

| Attempt | Status and failure boundary | Host seconds |
|---|---|---|
| Original 570s run | FAILED budget, Attention 921633/1188864 steps; no sealed att | runner 570.090650081 |
| Bounded v1 | FAILED setup, original Scalar FENV CDLL(None) admission omitted; no producer | runner 1.601585029; parent 1.849942664 |
| Bounded v2 | FAILED after sealed complete chain, frozen reference libc10.so hash read denied; 0 oracle tensor reads | runner failure snapshot 753.297448587; supervisor 755.145528056; parent 755.210739322 |
| Separate posthoc | PASS unchanged official BF16 contract; original FAILED untouched | inner 4.561150791; parent 4.616425806 |

The bounded execution used a 900s inner / 930s total outer envelope. Posthoc used a 60s inner / 90s total outer envelope. The reused native artifact was the identity-checked original C++ Matrix/SILU shared library, not a Scala/HostBlockTop/Verilator build. No native rebuild occurred; no compile cost is represented as an arithmetic speedup. DenseIdleV1 was not used.

## Numerical comparison

Frozen policy: `spec/numerical_contract.md`, SHA-256 `5cf7f538577e171ad42d70de60a24907b27e59991cc4d3895c42885fec962bb5`. BF16 operator limits stayed max_abs <= 0.03125 and mean_abs <= 0.005. The existing block budget was loaded but no block result was accepted. No approved FP32 or model-quality tolerance was invented.

| Node | Official pass | Bit exact | Different / observed | Max absolute error |
|---|---|---|---|---|
| n0 | True | True | 0/196608 | 0.0 |
| qr | True | True | 0/196608 | 0.0 |
| q | True | True | 0/196608 | 0.0 |
| kr | True | True | 0/32768 | 0.0 |
| k | True | True | 0/32768 | 0.0 |
| v | True | True | 0/32768 | 0.0 |
| kv | True | True | 0/65536 | 0.0 |
| scores | True | True | 0/99072 | 0.0 |
| logits | True | True | 0/99072 | 0.0 |
| prob | True | False | 1736/99072 | 2.2737367544323206e-13 |
| pv | True | False | 3/196608 | 0.0009765625 |
| att | True | False | 3/196608 | 0.0009765625 |
| softmax_fp32 | None | False | 88026/99072 | 2.384185791015625e-07 |

Six official prefix nodes (n0, qr, q, kr, k, v), KV, and actual causal scores/logits are bit exact. Probability differs in 1736/99072 positions; PV and att each differ in 3/196608. Therefore overall bit_exact=false. FP32 softmax remains diagnostic with official_numeric_pass=null; its 88026 differences are not promoted to official acceptance. The independent actual FP32 probability row-sum check passed: max error 7.248891051858664e-07, limit 2e-5, 1536 rows.

Causal fields expose 99072 actual positions out of 196608 logical positions; 97536 future positions stay unobserved and are never synthesized. PV/att have full 196608-element coverage. qraw/kraw/vraw have no official raw reference and retain null verdicts. x/cos/sin/repeat_k/repeat_v/mask are reference-only nodes. This is the existing 18-node Attention reference scope, not the separate 29-node full-block reference or full-block DUT acceptance.

## Actual work and fixed 4096 denominator

Counts originate from accepted software Matrix work and actual C++ std::fma calls. Every accepted Matrix step retains a fixed full-capacity denominator of 4096 FMA opportunities. The normal path actually executes 512 FMA per step. These ratios describe arithmetic work per accepted software step; they are not hardware utilization or busy time.

| Scope | Accepted steps | Actual executed FMA | Actual useful FMA | Steps x 4096 | Executed / full | Useful / full |
|---|---|---|---|---|---|---|
| qkv_dense | 98304 | 402653184 | 402653184 | 402653184 | 1 | 1 |
| attention_normal | 1188864 | 608698368 | 25362432 | 4869586944 | 0.125 | 0.00520833333333 |
| combined_matrix | 1287168 | 1011351552 | 428015616 | 5272240128 | 0.191825775656 | 0.081182875895 |

- Dense: 28 groups/done, 128 results, 98304 steps; QKV 28 partials, 14 drains, 16384 shared-vector adds; raw QKV ACK 1048576 bytes.
- Attention: 1188864 requests/results/normal steps; 105216 normal groups/done; 6144 PV32 held replies and retirements; 12288 half-output ACKs; 25362432 useful / 608698368 executed FMA = 1/24.
- Matrix owners acquired/released/responded: 29/29/29. Attention functional model ticks: 9096282; Host model ticks: 10150604. These are not hardware clocks. All hardware-cycle and hardware-busy measurements remain null.
- Attention physical read bytes 102236160, output write/ACK bytes 786432. Whole prefix+KV+Attention physical read bytes 116676544 and write/ACK bytes 4849664.

## Host phase timing

Exact intervals are differences of recorded monotonic stage entry timestamps; seconds below are displayed to nine decimals. The final comparison interval ends at the failure snapshot, not after failure serialization/parent teardown. Attention includes owner write ACKs; the next phase exports/validates bytes and holds pc12. The JSON preserves full recorded precision. Timing does not prove hardware throughput or a speedup over the incomplete old run.

| Stage | Start seconds | End seconds | Duration seconds |
|---|---|---|---|
| entry_until_first_stage | 0.000000000 | 0.029249527 | 0.029249527 |
| dependency_setup | 0.029249527 | 0.461604647 | 0.432355120 |
| source_and_input_hashes | 0.461604647 | 1.625390827 | 1.163786180 |
| native_artifact_validation | 1.625390827 | 1.631085836 | 0.005695009 |
| tool_hashes_and_fresh_setup | 1.631085836 | 1.727113604 | 0.096027768 |
| prefix_pc0_n0 | 1.727113604 | 9.356063475 | 7.628949871 |
| prefix_pc1_qraw | 9.356063475 | 49.069958379 | 39.713894904 |
| prefix_pc2_qr | 49.069958379 | 53.977550340 | 4.907591961 |
| prefix_pc3_q | 53.977550340 | 60.583866000 | 6.606315660 |
| prefix_pc4_kraw | 60.583866000 | 69.391477336 | 8.807611336 |
| prefix_pc5_kr | 69.391477336 | 70.217697064 | 0.826219728 |
| prefix_pc6_k | 70.217697064 | 71.388006805 | 1.170309741 |
| prefix_pc7_vraw | 71.388006805 | 80.223574875 | 8.835568070 |
| prefix_pc8_v | 80.223574875 | 81.048930841 | 0.825355966 |
| pc8_hold_and_kv_append | 81.048930841 | 82.105719659 | 1.056788818 |
| attention_observer_setup | 82.105719659 | 82.231850318 | 0.126130659 |
| attention | 82.231850318 | 751.520065349 | 669.288215031 |
| attention_writeback_and_pc12_hold | 751.520065349 | 753.076093676 | 1.556028327 |
| pc12_seal | 753.076093676 | 753.081819470 | 0.005725794 |
| post_seal_official_comparison | 753.081819470 | 753.297448587 | 0.215629117 |

Runner CPU at failure snapshot: 753.198198578s; runner peak RSS 515788 KiB. Separate posthoc peak RSS 542780 KiB. Native rebuild executed=false; native rebuild cost=0.

## Immutable evidence and publication

Final independent review binds 191 source files, all 77 original run files, 11 outputs, 30 observer raw/presence/count files, 9 input roles, 8 raw tensors, 3 input evidence files, 6 tools, 2 native artifacts, and 6 frozen reference runtime files. It verifies causal frequency/future sentinels, exact live KV copy, and PV-to-att layout. Review checked metric operand byte hashes and policy consistency without rerunning comparison.

Posthoc reads occurred only after seal and identity validation: 18 frozen reference tensors, the BF16 mask export, and a final rehash of those same 18 tensors (37 reads, 19 unique paths). Frozen runtime libraries were read for hash identity, not loaded into the posthoc process; Torch and DUT native service were not imported/loaded. Comparison NumPy was imported. Final identity hashes are explicitly appended posthoc checks, not invented original in-run final hashes.

The publication allowlist contains 22 newly added frozen v1/v2/posthoc source files, three FREEZE receipts, one existing 19-byte local .gitignore (housekeeping, outside executed source closure), and the two sibling result files: 28 files total. The original 169 already-tracked dependencies are untouched. Large receipts, raw captures, traces, logs, binaries, and runtime files remain under ignored work; only compact metadata and exact evidence hashes would be included in a future authorized publication. At local preparation time, these two result files had not been published; subsequent publication requires its own commit receipt. Frozen README files retain their historical NOT_EXECUTED statements; these sibling result files record the later outcomes without rewriting executed source bytes.
