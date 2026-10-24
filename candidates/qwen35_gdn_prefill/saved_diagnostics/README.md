# Saved Prep-g, chunk and suffix diagnostic checkpoint

This is a sanitized record and CLI-rooted helper adaptation of already completed
private Prep-g, head0/M64, head0/M128, and all16/M128 diagnostics on 2026-10-24. Preparing this
checkpoint did not load native arithmetic, run an owner, access weights, or run RTL.
No original production source, mathematical recipe, policy, or acceptance threshold
is changed here. The original execution remains UNKNOWN and is not continued.

Relocated native child/supervisor: TEMP_NOT_EXECUTED. Stdlib mapping/control/CLI tests
and post-comparison of previously completed head0/M128 and all16/M128 artifacts passed. These checks and
historical numerical PASS do not qualify the adapted native launcher or child.

## Acceptance boundary

- PASS, recipe identity only: all 2,048 saved Prep-g FP32 words match the independently
  evaluated exact-rational binary32 RNE Add/Mul/Div recipe bit for bit.
- DIAGNOSTIC_UNASSIGNED: saved Prep-g versus official output has 1,587 differing words,
  maximum absolute error 1.430511474609375e-6 and mean 6.69931829169932e-8. No Prep-g
  numerical acceptance threshold was assigned. This is not an official-operation
  attribution or complete floating-point flags oracle.
- PASS, this node slice only: head 0, tokens 0 through 63, 128 value columns, cold state,
  8,192 BF16 values. Six words differ, max 9.5367431640625e-7,
  mean 1.1937872912426428e-10. These meet the existing node max/mean bounds
  0.03125 / 0.005. BF16 bit identity is not claimed.
- PASS, M128 head0 slice only: tokens 0 through 127, two 64-token chunks in one cold
  diagnostic terminal, 16,384 nonzero BF16 output values. Seven words differ, max
  9.5367431640625e-7, mean 5.969114091897154e-11, meeting the same output thresholds.
- PASS, final after128 head0 state only: 16,384 nonzero FP32 values, 14,458 bit
  differences, max absolute error 7.450580596923828e-9, mean 2.33948623684253e-11.
  Every element meets abs(actual-reference) <= 1e-4 + 1e-4 * abs(reference), with
  zero violations. This is tolerance acceptance, not state bit identity.
- PASS, all16/M128 isolated chunk only: one original ChunkOwner/driver terminal,
  32 internal head-chunks, 262,144 BF16 output values. Fifty-five words differ,
  max 1.52587890625e-5, mean 9.90735132821996e-11, meeting the same node bounds.
- PASS, final after128 all16 state only: 262,144 FP32 values, 227,510 bit differences,
  max 9.5367431640625e-7, mean 1.230785461504479e-9. Every element meets the same
  1e-4 absolute plus 1e-4 relative state gate, with zero violations. Tolerance
  acceptance is not output/state bit identity.
- The extracted actual head0 output, final state, and first-chunk state digest are
  identical to the prior head0/M128 diagnostic. This is actual-to-actual consistency,
  not an additional official after64 state oracle.
- TEMP: state after token 63 still has no matching official state oracle. Full-block
  execution/acceptance, committed/published state, RTL, hardware cycles, effective MAC
  utilization, hardware QoR, and relocated native execution remain unvalidated.

`observed_metrics.json` contains small aggregate results, not raw tensor values.
The independent Prep diagnostic preserves the legacy magnitude/floor P7 ExpNegative
plus Softplus7 recipe; the experimental chunk split-ln2 exp does not replace Prep op4/op7.
Decimal exp/log at 70 and 100 digits is a precision-stability diagnostic, not a proof
of correctly rounded transcendental semantics. Counterfactual factor replacements
cannot identify the observed official factors because those factors were not captured.

## Historical chunk scope and resources

The actual input was the first 64 or 128 rows of an already saved real Prep result, not zeros,
a generated fixture, a Prep rerun, or an original receipt replay. Diagnostic writes
and ACKs rehydrated TypedMemory. Each diagnostic used one ChunkOwner/driver terminal,
heads=1 (head0 slices) or heads=16 (all16/M128), key/value dimensions=128, host_batch=true,
cold state, IEEE finite gradual
underflow policy, fatal mask 28, finite_mul_tininess_r2, experimental P7 split-ln2 exp,
legacy ascending FP32 cumsum, and row1_streaming matmul. The actual child was blocked
from reference access. Comparison occurred only after supervised completion and cleanup.

For M64, native candidate wall time was 13.013652981026098 seconds; the supervisor took
14.323243860038929 seconds. One CPU, 512 MiB address-space and sampled-RSS caps,
60-second CPU/compute allowance, and 75-second outer budget were used. The child exited
naturally with code 0. The retained leader was reaped only after two complete owned-group
absence scans. All 1,101 historical pins remained stable. These are local software
observations, not end-to-end acceleration or measured hardware utilization.

For M128, candidate and supervisor times were 26.241959984006826 and
27.35001520602964 seconds. One CPU, the same 512 MiB caps, 90-second CPU/compute and
110-second outer budgets were used. Natural exit was 0, retained-leader cleanup was
confirmed, and all 1,106 historical input pins were stable. Observed second-chunk
reads of the actual first-chunk state were predict_matmul=65,536, inter_matmul=65,536,
and state_decay=1,024 beats, with two chunks completed. No after64 official state
comparison is implied. Official output0020 is [1,128,16,128] BF16 with head0 selected
at each token stride. Official state0021 is [1,16,128,128] FP32 after128; head0 is its
first 65,536 bytes. The complete state0021 and final-cache0043 blobs are identical.

For all16/M128, candidate and supervisor times were 430.2692614609841 and
431.0102035700111 seconds. One CPU, 1 GiB address-space and sampled-RSS caps,
600-second CPU/compute and 660-second outer budgets were used, with 60 seconds
reserved for cleanup/receipts. Natural exit was 0, strict retained-leader cleanup
was confirmed, and all 1,106 historical input pins remained stable. All 16 heads
completed two internal chunks in the single terminal; each head had the same
65,536/65,536/1,024 second-chunk carry-read counts. Full contiguous output0020 and
state0021 were compared, not head0-strided slices. The dimensions match production
geometry, but this is still an isolated software diagnostic: state was not committed,
output/state were not published, and generation was not advanced. The reused helper
preserves per-head/chunk completion and carry progress plus file/directory fsync.
These local wall times and software head-chunk counts are not hardware cycles,
utilization, or full-block acceleration evidence.

## What is and is not included

Included: stdlib diagnostic/comparison/preparation/supervision helpers, relative source
pins, model/input digests, one canonical selected-runtime-tree digest, and aggregate
metrics. No weights, NPZ, raw actual/reference/state data, private paths, process receipts,
PID or inode records, native binaries, or runtime tree are included.

The helpers are not a standalone model implementation. Supply separately:

1. The exact original repository source closure at commit
   `1f5b1c203767f48345ce324685dba539eeee7a4f`, matching the recorded source hashes.
   The current independent checkpoint is not that original source closure.
2. For Prep-g: the saved cold diagnostic directory containing its original `pins.json`
   and `snapshot/` tree; the exact payload directory containing `linear_attn.A_log.bin`
   and `linear_attn.dt_bias.bin`. These remain private and are read from CLI paths.
3. For the chunk: the saved full Prep FP32 file, its pinned provenance JSON files,
   and the separately captured official M128 BF16 chunk output. No checkpoint/Torch
   weights are needed for this isolated replay, but the real saved inputs are required.
   M128 additionally requires the pinned official state0021, final-cache0043, capture
   manifest, and original native/capture.py source identity. These are not needed for M64.
4. For native chunk execution: the selected Python interpreter, NumPy/yaml site tree,
   R2 vector library and metadata, compiler identity, and the original pinned
   `scripts/idma_source_export_20261017/strict_cleanup.py`. Preparation does not compile
   or install them. The runtime pin set is not a complete OS/runtime closure.

`pins.json` records the historical script and plan SHA-256 values for traceability.
The relocated helpers are adaptations, not byte-identical historical executables.
The historical 1,101/1,106 counts are not the counts of newly prepared relocated plans:
new helper/source snapshot pins differ, and machine-specific Git metadata is not reused.
The selected 912-file runtime digest is compact UTF-8 JSON of sorted
`[relative_posix_path, byte_count, sha256]` rows, excluding `__pycache__` and `.pyc`,
within `numpy`, `numpy.libs`, and `yaml`. No runtime content is bundled.

## Explicit opt-in reproduction

Use private output directories outside the source, runtime, and checkpoint trees.
The original frozen working tree and unrelated processes must not be modified or signaled.
The examples below are templates; variables must resolve to separately supplied inputs.
The preparation and launch commands below were not executed to prepare this checkpoint.

```sh
python diagnose_prep_g.py \
  --repository "$SOURCE_REPO" --saved-snapshot "$SAVED_COLD_DIAGNOSTIC" \
  --payload "$PAYLOAD" --output "$NEW_PREP_DIAGNOSTIC"

python prepare_chunk.py \
  --repository "$SOURCE_REPO" --runtime-site "$RUNTIME_SITE" --python "$PYTHON_BIN" \
  --vector-library "$VECTOR_LIBRARY" --vector-metadata "$VECTOR_METADATA" \
  --compiler "$COMPILER" --saved-prep "$SAVED_PREP_FP32" \
  --saved-pins "$SAVED_PINS_JSON" --saved-progress "$SAVED_PROGRESS_JSON" \
  --official-output "$OFFICIAL_CHUNK_BF16" --cpu "$ALLOWED_CPU" --output "$NEW_CHUNK_DIR"
```

The default is --tokens 64 --heads 1. To prepare head0/M128, append all of these
arguments to the prepare_chunk.py command above:

```sh
--tokens 128 --official-state "$OFFICIAL_STATE_0021_FP32" \
  --official-final-cache "$OFFICIAL_FINAL_CACHE_0043_FP32" \
  --official-manifest "$OFFICIAL_CAPTURE_MANIFEST"
```

To select all16/M128, also append `--heads 16`. Only heads 1 or 16 are admitted,
and heads 16 requires tokens 128. It selects the historical all16 address map and
resource bounds, full contiguous output/state mapping, and every-head carry checks.
No arbitrary head subset, larger token count, or policy change is supported.

State inputs are mandatory only for M128 and rejected for M64, because the after128
oracle must never be treated as an after64 oracle. The same child, supervisor, and
comparator select their bounded case from the reviewed plan. Policies are unchanged.

Review the generated private PLAN.json and its printed digest first. Preparation only
hashes/snapshots/slices inputs; it does not launch. Launch defaults to preflight only.
A separate explicit `--execute` is required for numerical execution:

```sh
python launch_chunk.py --plan "$NEW_CHUNK_DIR/PLAN.json" --reviewed-plan-sha256 "$PLAN_SHA"
python launch_chunk.py --plan "$NEW_CHUNK_DIR/PLAN.json" --reviewed-plan-sha256 "$PLAN_SHA" --execute
python compare_chunk.py --plan "$NEW_CHUNK_DIR/PLAN.json" --reviewed-plan-sha256 "$PLAN_SHA" \
  --output "$NEW_CHUNK_DIR/comparison.json"
```

The supervisor is single-use with no automatic retry. It preserves live retained-leader
identity, boot/session/process-group ownership, exact-input pre/post checks, deadlines,
resource caps, bounded output, and the original strict cleanup helper. It does not
poll/reap before the helper's two complete absence scans. An unverified cleanup or
uncertain outcome leaves the observation UNKNOWN/INCOMPLETE, never a numerical FAIL
solely because cleanup is uncertain. The supervisor may reject admission or report
operational failure; that is not a numerical verdict and gives no permission to
retry or signal an unrelated process.
Audit hooks guard accidental access; they are not a native-code security sandbox.
Generated plans and run outputs contain private evidence and must never be committed.
The comparison applies the existing node thresholds to the selected head0 or all16
output; M128 additionally applies the existing per-element state gate to the matching
final after128 state. It cannot promote full-block, state-commit, after64-state, or
RTL acceptance, or qualify the adapted native child/supervisor.

## Lightweight checks performed for this extension

```sh
python -I -S -B -m unittest discover -s candidates/qwen35_gdn_prefill/saved_diagnostics \
  -p 'test_chunk_cases.py' -v
```

Twenty-one stdlib tests passed: bounded heads/tokens and all16 resource/address
configuration, default head0/M64 preservation, CLI state requirements, token-strided
head0 versus full contiguous output/state mapping, extent/cache identity, every-head
carry completion/read counts and first-state identities, every-element state tolerance
(including the final head, not aggregate-only), nonfinite rejection, native-independent
CLI help under -I -S -B (plus child import-only), durable file/replace/directory fsync
ordering, all16 heartbeat progress and 32-head-chunk terminal admission with head0
behavior preserved, and fail-closed cleanup admission.
Synthetic comparator fixtures test control flow only, not numerical owner correctness.
Source AST and JSON parse checks passed. A separate adapted comparator run over the
already completed private head0/M128 and all16/M128 artifacts reproduced every historical result field,
except its own script hash and comparison duration; all input pins remained stable.
Each wrote only a fresh private comparison file. No preparation, candidate, native owner,
model, supervisor execution, or Prep arithmetic was rerun for these checks.

## Saved suffix diagnostics: GatedNorm, ordinary O, residual → post_norm

The following historical M128 outputs independently passed the unchanged node gates
(maximum 0.03125, mean 0.005), with natural exit 0, stable pins and strict retained-leader
cleanup. No owner was rerun for this checkpoint. Counts are BF16 values/word differences:

| Stage | Values | Max absolute | Mean absolute | Word differences | Local seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| GatedNorm | 262144 | 0.001953125 | 1.6022426052586525e-8 | 56 | 30.3487 |
| Ordinary O | 131072 | 0.00048828125 | 1.922579855317963e-7 | 671 | 20.9059 |
| Attention residual | 131072 | 0.00048828125 | 1.8699574866332114e-7 | 273 | 2.7118 |
| post_norm | 131072 | 0.015625 | 6.4033083617687225e-6 | 290 | 4.5712 |

GatedNorm consumes saved actual Chunk/Z; O consumes saved actual GatedNorm and uses
original ordinary single-K sequential FP32 FMA, never IndependentK512. The pair
consumes saved actual O, then original Add output directly feeds original
Torch210CpuDefault1024 RMS through the same physical TypedMemory region and Scalar.
Only that pair has resident handoff evidence. Earlier boundaries are diagnostic
rehydrations, not a single resident full-block lifecycle. Block generation remains 0;
there is no state/history commit, full-block acceptance, RTL or utilization claim.
The original full_m128_02 execution remains UNKNOWN.

One fixed-case adapter shares loading, driving and receipt control. It reuses the
existing supervisor's ownership/deadline/cleanup core and the chunk comparator's
BF16 metric reducer. `suffix_pins.json` adds relative artifact digests and named
configurations; source/runtime identities reuse `pins.json`. Original numerical
sources are neither copied nor modified. The suffix source-identity guard permits
only the original bounded read-only Git calls, without replacing source_identity.

All relocated native preparation/launch/child paths remain TEMP_NOT_EXECUTED.
Historical artifact comparison does not qualify them. Thirty-four stdlib tests
passed, including the original 21 chunk tests, isolated CLI help/import checks,
fixed-case and cleanup/terminal rejection, opaque weight transpose, and constructor
acquisition ordering. Historical comparator parity was checked for all four outputs.

Preparation requires a fresh separate source checkout, the pinned runtime, explicit
JSON path maps, and a fresh private output directory. Each map is a JSON object from
name to supplied local path. Input names: GatedNorm `core,z,weight`; O
`gated_norm,weight_nk` (KN is generated by bit-preserving transpose); pair
`hidden,o,weight`. Reference names are `gated_norm`, `o`, or both
`attention_residual,post_norm`. These exact saved files are not included here.
Scalar cases require detached HEAD at the recorded source commit and the pinned Git
binary. O requires an existing matching Matrix library/build receipt; preparation
never builds it. Do not target the original frozen working tree or reuse run receipts.

```sh
python -I -S -B prepare_suffix.py --case "$CASE" \
  --repository "$FRESH_SOURCE_REPO" --runtime-site "$RUNTIME_SITE" \
  --python "$PYTHON_BIN" --compiler "$COMPILER" --cpu "$ALLOWED_CPU" \
  --inputs "$INPUT_PATH_MAP" --references "$REFERENCE_PATH_MAP" --output "$NEW_SUFFIX_DIR"
# For Matrix cases o, gate_up, final_triplet, append --matrix-library "$MATRIX_LIBRARY" --matrix-receipt "$BUILD_RECEIPT".
python -I -S -B launch_chunk.py --plan "$NEW_SUFFIX_DIR/PLAN.json" --reviewed-plan-sha256 "$PLAN_SHA"
# Native execution additionally requires explicit --execute; it was not run here.
python -I -S -B compare_suffix.py --plan "$NEW_SUFFIX_DIR/PLAN.json" \
  --reviewed-plan-sha256 "$PLAN_SHA" --output "$NEW_COMPARISON"
# Alternatively, authenticate and compare only an already completed reviewed bundle:
python -I -S -B compare_suffix.py --historical-case "$CASE" --bundle "$SAVED_BUNDLE" --output "$NEW_COMPARISON"
python -I -S -B -m unittest discover -s . -p 'test_*cases.py' -v
```

`CASE` is exactly `gated_norm`, `o`, `residual_post_norm`, `gate_up`, or
`final_triplet` (the last two are described below). Private generated plans
and native receipts must stay outside Git. Audit hooks are not a native-code sandbox.

## Saved final suffix and cold actual-boundary chain

Five further historical M128 node outputs passed their existing gates. No owner was
rerun for this checkpoint; relocated native preparation/launch/child paths remain
TEMP_NOT_EXECUTED even where stdlib tests and saved comparison parity pass.

| Stage | BF16 values | Max absolute | Mean absolute | Word differences | Local seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gate | 458752 | 0.015625 | 1.8651137647144162e-5 | 8636 | 16.581868 |
| Up | 458752 | 0.0078125 | 1.3680442634722567e-5 | 13496 | 17.420115 |
| SiLUMul | 458752 | 0.0078125 | 3.129680926861056e-6 | 17603 | 39.103893 |
| Seeded Down | 131072 | 0.0009765625 | 4.963985887229683e-6 | 10051 | 30.567868 |
| Final output | 131072 | 0.001953125 | 5.045527416314144e-6 | 5770 | 1.095899 |

Final output uses max 0.05 / mean 0.01; all other listed nodes retain max 0.03125 /
mean 0.005. Prep has no assigned numerical acceptance threshold. Numerical failure,
incomplete execution, and the original run's UNKNOWN status are not interchangeable.

Gate and Up share one ordinary Dense owner, Matrix, actual post_norm input,
TypedMemory and bank storage, with one initial reset and no prefix. Each executes
469762048 FP32 FMAs. The final triplet has genuine SiLUMul -> Down -> Add handoffs
through the same allocated storage. Original Down uses K2560+1024, a private
unpublished 524288-byte FP32 prefix, 8192 prefix reads/seed beats, 32 seed ACKs,
64 results, 14 groups/done, 114688 steps, and 469762048 FMAs. It does not use
IndependentK512. The original Matrix build is reused; no compile is part of prep.
Historical supervisor times are 35.608069 s for Gate/Up and 72.734784 s for the
triplet. Natural exit 0, retained-leader cleanup and independent postflight passed.
These facts describe those saved diagnostics, not new execution of this adapter.

The new cases are `gate_up` and `final_triplet`, using the same CLI above. Both
require `--matrix-library` and `--matrix-receipt`. Explicit input maps contain:

- Gate/Up: `post_norm,gate_weight_nk,up_weight_nk`; references `gate,up`.
- Final triplet: `gate,up,attention_residual,weight_nk`; references
  `silu_mul,down,output`.

All NK weights are original opaque BF16 words transposed to KN with inverse-map
verification, not numerically converted. The triplet's exact source-identity
allowance is four original Elementwise Git reads; Gate/Up allows none. Source and
runtime closures remain the relative digests in `pins.json`; `suffix_pins.json`
adds the reviewed private artifact hashes, never their contents or absolute roots.
Original model and arithmetic sources are untouched.

`cold_chain_pins.json` sanitizes the historical chain into logical bundle names,
relative artifact paths, digests, edges and aggregate metrics. Its 13 actual
predecessor-to-consumer edges and 62 selected artifact pins match before and after
checking. It covers 15 BF16 stage outputs plus history staging, Prep provenance,
and isolated after128-state numerical diagnostics. It is not a completion seal:
the six original prefix owner terminals came from full_m128_02, which remains
UNKNOWN. Later separate diagnostics and saved-boundary rehydration cannot establish
a single-resident full-block lifecycle, joint state/history commit, generation
advance, RTL or hardware utilization. Preparation of another full run does not
qualify this adapter or change any of those limitations.

Use a private JSON object mapping `prefix,chunk,gated_norm,o,residual_postnorm,
gate_up,final_triplet` to their explicit saved bundle roots, then run:

```sh
python -I -S -B check_cold_chain.py --roots "$PRIVATE_ROOT_MAP" --output "$NEW_CHAIN_CHECK"
```

Forty-one stdlib tests pass, including the prior 34 and new genuine Down receipt-schema, fixed-case, stage admission,
seed/prefix rejection, final-output threshold, CLI and sanitized-chain checks.
The reused comparator independently reproduces all five new saved node metrics;
the chain checker reproduces all 13 edges with stable selected pins. These checks
import no numerical model and execute no native arithmetic, owner, launcher or build.
