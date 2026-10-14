# Qwen2 M128 full-block official-AST source candidate

Status: **FROZEN REFERENCE METADATA / BOOTSTRAP REVIEWED / NOT DUT ACCEPTANCE**.
Default recipe/guard CLI checks pinned source, JSON metadata, AST identities and
payload sizes using CPython 3.12 stdlib only. It neither imports Torch/NumPy/
Transformers nor opens raw, producer or reference payloads. Explicit numerical
entry is guard.py only, after independent review plus a one-use parent go receipt.
The single successful bootstrap has been independently reviewed. This revision
pins all 29 observations in FROZEN_CONTRACT.json; it does not by itself establish a
fresh reproduction. CPython other than 3.12 is unsupported.

This new package leaves the published M128169-file and M16188-file execution
closures unchanged. Their exact SHA256 ledgers are in pins.json and checked
read-only. It does not change or inherit the outcome of either Attention run.

## Allowed cold checks

From the repository root:

    python -B candidates/qwen2_fullblock_reference_m128/recipe.py
    python -B candidates/qwen2_fullblock_reference_m128/recipe.py --action plan
    python -B candidates/qwen2_fullblock_reference_m128/test_cold.py

No output directories are created by recipe.py. Cold tests write only under
work/qwen2_fullblock_reference_capture_20261014 and use stdlib fake processes.
The additional cold suite is:

    python -B candidates/qwen2_fullblock_reference_m128/test_lifecycle.py

recipe.py execution/input/output/authorization flags still refuse. Direct
capture() calls fail without a live inherited pipe, exact parent wrapper command,
isolated worker process group, source manifest and fresh GO binding. The supported
parent command is exactly Python -B, the guard script, then --mode, --run-id and
--go in the documented order. Relative and absolute script paths resolve against
the real parent cwd to the same pinned file; /proc/exe binds the interpreter.
Python -c/-m, path mentions outside the script slot, and mismatched option values
are refused before raw loads or numerical imports. A flags or
pins/ADMISSION edit alone cannot bypass the wrapper. This is accidental-misuse
protection, not a security boundary against a malicious same-uid process capable
of changing code or impersonating the wrapper.

## Official source and scope

Model checkpoint: Qwen/Qwen2-1.5B-Instruct, layer0, revision
ba1cf1846d7df0a0591d6c00649f57e798519da8. Official Transformers source is v4.40.1,
commit9fe3f585bb4ea29f209dc705d269fbe292e1128f. The exact existing source/config,
header and raw range manifests are pinned, as are original PyTorch SiLU/Linear
Python sources and native runtime identities. No download or installation is
part of this candidate.

The existing27 Qwen2 AST nodes remain intact. Added11 whole Qwen2 nodes are the
MLP class168–180, o_proj constructor231, decoder constructors730/732, original
residual763, o_proj313 and decoder776/779/780/781/782. The exact14-node activation
closure comprises12 unchanged ClassDefs plus original ACT2CLS and ACT2FN
assignments. The vendored activations.py is byte-for-byte the acquired official
source (SHA25610c37e915ce2b52d539a5b52ecaaf644e2b0c56d282db00778098d74342ebeee,
Git blob2355fb5fed678d0de6e2c53f52644a35a691a34e); SOURCE_RECEIPT.json is preserved
unchanged. Its original `silu: nn.SiLU` mapping, selected by original Qwen2MLP,
is used. No hand-written activation or substituted official expression is used.

Count distinction: **38 model nodes +14 activation nodes**, yielding29 named
boundaries. This remains an official AST subset with explicit wrapper holders and
handoffs. Complete Qwen2Attention.forward, Qwen2DecoderLayer.forward, DynamicCache,
the full model and Transformers imports are excluded. Rotary cache is explicitly
bounded256, while original config says32768; equivalence is not claimed.

## Raw-only plan and dtype boundaries

The proposal joins the pinned prefix8 and tail5 original raw manifests by exact
checkpoint/name/shape/dtype/range/hash, preserving their different schemas.
Input14 producer receipts are checked as metadata and file sizes only. Their
payloads are never arithmetic inputs to this reference. In particular gamma1 is
read as original BF16 raw, not the materialized FP32 gamma1 producer. Matrices
are loaded in original checkpoint shapes. No old reference, typed output,
actual result, zero substitute, intermediate preload or reconstructed historical
arena is read to compute an output.

All original parameters are replaced with fixed raw BF16 values and checked
before arithmetic; holders are eval and require_grad=False. Original RMSNorm
performs FP32 norm work, casts to BF16 and multiplies direct BF16 gamma. Original
QKV/RoPE/Attention, o_proj, residuals and MLP return native BF16. Original
softmax expression300 runs unchanged; a one-call return tracer observes its FP32
softmax result before the original BF16 cast. Existing tracers are refused.

Original MLP180 remains whole. Forward hooks observe gate, SiLU, up and down;
the down pre-hook observes the product. Exact hook order/count is
`gate, silu, up, act, down`, once each, and all hooks are removed in finally.
Observers record source tensor stride/storage metadata before copying; copied
values are not fed back into computation. The wrapper name handoff after
original313 is disclosed. Original763 saves x and original779 saves r.

The explicit BF16 mask is wrapper data, not an executed official mask helper or
a DUT-produced tensor: allowed/diagonal+0, future0xff7f. Its native/export hashes
remain separately pinned. cache_k/cache_v are **cold semantic aliases; DynamicCache
not executed**, captured before repeat_kv. Cache K equals fresh K exactly; cache V
has a fixed head-major/token-major equality with fresh V. All layout transforms
are named in pins.json, never selected by comparison error.

## Outputs and honest freeze status

29 names: x, n0, qr, q, kr, k, v, cos, sin, repeat_k, repeat_v, mask, scores,
logits, softmax_fp32, prob, pv, att, cache_k, cache_v, o, r, n1, gate, up, silu,
act, down, y. All native BF16 except softmax_fp32. BF16 exports use exact FP32
widening; softmax_fp32 is exported unchanged. Native hashes are computed from
logical contiguous native bytes, while stride/storage/contiguity describe the
actual observed native tensor.

The original pins.json geometry templates deliberately retain null hashes/layout
observations and NOT_CAPTURED labels. They are not the frozen comparator. The
separate code-pinned FROZEN_CONTRACT.json contains the independently reviewed
29 records, bootstrap manifest+seal identities and exact review identity. Prior18
expectations remain separate, unchanged fresh reproduction checks. Bootstrap v2
is sealed as observations only. A fresh REFERENCE.json requires a new single go
and a distinct raw-only reproduction; no result is inferred from metadata alone.

Freeze review: work/qwen2_fullblock_reference_capture_review_20261014/
bootstrap_v2_review/BOOTSTRAP_REVIEW.json, SHA256
b5baa8bdeaa2a4b1faff81fc01a454588164a8ffbc9a2c07057360d80a2f7ddb.
The original executed 13-file source snapshot is preserved under the ignored
capture work/v2_cli_fix/frozen_sources; v1 failed evidence is also retained.

## Storage admission

Exact FP32 export total32,571,392B plus native mask32,768B =32,604,160B per
capture. One bootstrap plus one separate frozen reproduction =65,208,320B of
payloads. Planned caps:34MiB per capture (35,651,584B),69MiB total (72,351,744B),
leaving7,143,424B for bounded source/boundary manifests, review and logs. The
future body accounts for bytes before publication. There is no second full native
dump. Raw13/role14 files and native runtimes stay in place. These disk totals are
not RSS or wall-time estimates, and do not cover a separate whole-block DUT run.

## Admission and remaining review

ADMISSION.json describes the lifecycle, not permission. Only the parent launches
an actual capture after independent source review and an explicit single go. No
automatic retry occurs. An existing successful or failed output is never reused.

1. Review this exact SOURCE_MANIFEST.json and the original 27+11 model nodes,
   14 activation nodes, all output layouts, dtypes, copy/mask/causal semantics and
   SiLU hooks. All original 18 fields, including native metadata, remain exact
   fresh-prefix reproduction checks.
2. The independent source review JSON must contain status
   APPROVED_SOURCE_FOR_SINGLE_BOOTSTRAP (or FROZEN), mode bootstrap (or frozen),
   source_manifest {bytes, sha256}, numeric_executed false, a distinct reviewer,
   and tool_identity {python_executable: the full pinned native Python record,
   implementation: cpython, python_major_minor: [3,12], source_manifest}.
3. The parent creates one bounded JSON go in the capture work area with exact
   schema 1; action single-bootstrap or single-frozen; run_id; source_manifest;
   source_review {path,bytes,sha256}; issued_by; maximum_invocations 1;
   no_retry true; exclusive_numeric_slot true. The last field attests that other
   numerical jobs are terminal. Review files may live in this work area or the
   separate qwen2_fullblock_reference_capture_review_20261014 review area.
4. Only after that go, the parent runs exactly once:

       python -B candidates/qwen2_fullblock_reference_m128/guard.py --mode bootstrap --run-id PAIR_ID --go work/qwen2_fullblock_reference_capture_20261014/GO_FILE.json

   Outputs are reserved fresh as capture work/PAIR_ID/bootstrap. The wrapper
   supplies the pinned environment; no external runner toggles capture flags.
   The independent numerical child writes OBSERVATIONS.json, never a seal.
   The wrapper checks full inventories and before/after identities, publishes
   BOOTSTRAP_REFERENCE.json and atomically publishes SEAL.json last. The seal is
   observations only and explicitly unaccepted. A failure retains its actual
   stage, error, partial file identities and resource/log records without a seal.
5. After independent bootstrap review, a separate source change may add
   FROZEN_CONTRACT.json and pin its exact digest in recipe.py's
   FROZEN_CONTRACT_SHA256. Its schema is {schema:1,
   status:FROZEN_FROM_INDEPENDENT_REVIEW, bootstrap_manifest:{path,bytes,sha256},
   bootstrap_seal:{path,bytes,sha256}, review:{path,bytes,sha256}, outputs:{all29}}.
   The review must be APPROVED_FOR_FREEZE, identify the same bootstrap manifest
   and seal, reviewer, and outputs_sha256 over canonical encoded outputs.
   No CLI/caller-provided expected hashes are accepted. Bootstrap data never
   teaches a running comparator new accepted values.
6. Independently review the new frozen source manifest, then issue a separate
   single-frozen go and run guard.py --mode frozen in PAIR_ID/frozen. It loads
   original raw13, not bootstrap payloads, in a fresh numerical process. It checks
   exact29 code-pinned frozen identities and original18 metadata/hashes afresh.
   Successful reproduction remains reference-only, never DUT acceptance.

## Bounded lifecycle details

BUDGET.json records static byte accounting and the existing reference evidence:
M128 attention reference 5.978s; M16 attention reference 805,957,632B peak RSS /
6.001s. Added tail raw+BF16 parameters, initial FP32 MLP allocation, output/hook
copies and export bytes give conservative additive accounting 1,205,602,304B,
not a predicted or measured new full-block peak. Native runtime hashes stream
1MiB chunks, avoiding a former 443,509,856B temporary read. No failed DUT budget
is used and no new numerical measurement has been made.

The 120s absolute deadline starts at guard.run entry, before source/go/raw/runtime
preflight. It is never reset. The numerical child gets only remaining time;
postflight hashes and publication are included. A separate watchdog covers the
wrapper and its child tree with a 122s outer deadline (120s work plus at most 2s
cleanup allowance). Receipts report both limits and elapsed measurements; no
claim of an exact 120s terminal bound is made. In production the inner local
watchdog is disabled because the independent outer watchdog covers the complete
lifecycle; the receipt explicitly records both facts.

The 1.5GiB RSS guard samples the numerical process group plus discovered/adopted
descendants every 20ms. It excludes the wrapper/watchdog and is not an OS hard
memory cap. A Linux subreaper, killpg, identity-checked descendant kills and bounded
reaping cover workers and observed setsid/fork descendants. Remaining descendants
block success. The production numerical child refuses Python-level fork/exec/
subprocess events. Malicious native double-forks between samples are outside this
trusted-code contract; no cgroup containment is claimed.

Each log stream retains at most 64KiB (128KiB total). Full observed byte counts,
SHA256, retained SHA256 and truncation flags are recorded; 16MiB aggregate emitted
logs fail the run. Disk is statically admitted and sampled, not a filesystem
quota. The fixed export payloads remain exactly 65,208,320B for the pair, within
34MiB/run and 69MiB/pair including bounded metadata/logs. Raw/weights stay ignored.
CPython executable, native libraries, original raw13, source dependencies and the
whole package manifest are frozen before/after. Producer14 remain metadata/stat
only. No downloads, DUT/RTL runs, external compiler or CI launch are provided.

An actual full-block driver is a separate task and contract. Its own raw-only
single launch, FullGraphMemory/SharedWorkspace, terminal/ACK observations and
post-seal oracle opening are not implemented here. Frozen reference arrays cannot
prove DUT29 coverage. Keep missing mask and97,536 unobserved future positions per
Attention field explicit; current observed causal positions are99,072 per field.
Native bit-exact acceptance and official tolerance acceptance remain separate.
Unchanged numerical policy: BF16 operator max_abs<=0.03125 AND mean_abs<=0.005;
y block max_abs<=0.05 AND mean_abs<=0.01; every assigned hidden gate must pass;
no NaN/Inf; exact mask/cache copy/layout semantics; softmax row-sum error<=2e-5.
softmax_fp32 remains DIAGNOSTIC_NO_APPROVED_FP32_TOLERANCE, passed=null. This
candidate claims no model/RTL execution, cycles, bandwidth, utilization or QoR.
