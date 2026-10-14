# Read-only posthoc comparison of sealed M128 v2

Status: NOT_EXECUTED until a new independent review and parent go. This package
does not execute or resume the DUT. It appends a separate comparison receipt for
the exact sealed output of m128_pv32_bounded_actual_v2. The original run remains
FAILED and its RESULT/launch/progress/all 77 files and 185 sources are immutable.

## Exact failure and evidence

The v2 chain finished all 1188864 Attention requests/results, 608698368 executed
normal FMAs, full 786432-byte Attention ACK coverage, and pc12 held with 11 owner
results and 12 public completions. All backend debts were zero. The actual output
seal is true; public Attention visibility and original acceptance are false.

The later reference metadata check tried to hash the first of its six pinned
runtime files, work/runtime_recovery/site-packages/torch/lib/libc10.so. Its exact
size is 1403600 bytes and SHA256 is
7dc289cfb287f751eb8586c275022dba56979dd9e769cd01b73b2993f3442c84.
The v1/v2 gate's old-work native-file rule rejected that read. The recorded
oracle gate had been opened, but oracle_reference_reads was still empty. No
official reference tensor had been consumed and no numerical verdict existed.

The original RESULT digest is
38b59e30edcf655300ce3b7c5342809641589edc327482e4ae781e959c04947e.
The independent V2_ACTUAL_SEAL_REVIEW.json is separately hash-pinned, including
its 77-file inventory, full observer causal/frequency/future-sentinel validation,
PV-to-Attention layout, KV exact-copy, input/raw/tool/native/runtime identities.

## Read-only recovery contract

1. Validate the exact original FAILED receipt and parent launch, original 185
   sources, successful owner/ACK/held boundaries, same-live identities, source
   before/after-failure equality, observer completion and pristine suffix.
2. Rehash all 77 original files, the 11 output files, all 30 observer data files,
   nine inputs, eight raw source tensors, six original runtime tools, two native
   code artifacts, and six frozen reference-runtime files. The latter are read
   only to verify identity, never loaded or executed.
3. Build FrozenCapture from the original shape, observed-presence bytes and raw
   u32 data. It is an immutable file adapter, not a fabricated live observer or
   producer. Recheck frequencies, live K+V bytes and PV-to-Attention layout.
4. Only after those checks open the eighteen original frozen reference tensors
   using the unchanged original reference gate. Call the original
   compare.official and original load_policy/compare/stage_verdict functions.
5. Recheck sources, original receipts/inventory, inputs/raw/evidence, tools,
   native artifacts and reference payloads afterward. These are explicitly
   appended posthoc checks because the original run did not reach final hashing.

Input provenance is checked against the exact original execution receipt and
hash-bound independent review. The input materializer is not rerun: its old
RoPE generator ELF and gcc --version are not required to compare already sealed
outputs, and the posthoc process grants neither execution path. The original
reference metadata/payload validation functions are called unchanged.

No arithmetic/owner/runtime() function is called. No Torch module is imported,
no Matrix or Scalar service is constructed, no DUT or Torch native library is
loaded, no compiler runs, and no model input is used as a DUT operand.
The existing NumPy comparison runtime is imported from its verified tool path.
Input bytes are read only for identity verification. NumPy computes comparison
metrics and the original probability-sum audit; that is not a DUT recomputation.

The bootstrap guard forbids Torch/DUT imports, subprocesses, and writes outside
the new output while pinned NumPy and comparison modules load. The full audit
gate then denies all ctypes.dlopen, allows only exact pinned runtime/tool reads,
rejects unknown old-work payloads/libraries, keeps oracles closed until the seal
checks, and allows writes only inside the fresh posthoc output. It is a Python
audit/read-path boundary, not an OS/native-syscall sandbox.

## Acceptance and limits

The original numerical gates are unchanged: six official producer nodes, KV
exact-copy, causal scores/logits/probabilities, complete PV/Attention, the 2e-5
probability-sum condition, and the original BF16 policy. FP32 softmax remains a
diagnostic with no invented official tolerance; qraw/kraw/vraw still have no
official reference. Future causal positions are not filled in.

A successful new receipt is POSTHOC_OFFICIAL_COMPARISON_PASS_PC12_HELD. It never
changes the old run to PASS, publishes att, retires pc12, or claims finalfence,
full-block/29-node acceptance, hardware cycles, RTL, or EDA.

## Cold validation and one proposed execution

Default entry is NOT_EXECUTED. Seven cold tests cover exact seal admission,
eight altered-seal failures, exact runtime/old-write/library restrictions,
nineteen early-oracle failures, a real audit-hook libc10 read, real comparison
dependency imports, exact nine-input/eight-raw identity checks, and the original
reference-metadata validation path with six runtime hashes. A real audit-hook
positive test completes the entire pre-oracle preparation, including all 77
original files, 41 sealed output/observer artifacts, FrozenCapture and PV layout,
then stops with oracle reads still empty. No reference tensor or compare.official call occurs
in the cold suite. Both normal and optimized Python are tested.

The exact independently reviewed command is in FREEZE.json. Its only proposed
output is work/qwen2_live_attention_numeric_m128_bounded_20261014/posthoc_v2_compare_v1.
The inner deadline is 60 seconds from admission. The external supervisor sends
TERM at 85 seconds and KILL after at most five more, for a 90-second outer bound.
Only the parent invokes it once after go. No stage, commit, push, or DUT retry is
part of this preparation.
