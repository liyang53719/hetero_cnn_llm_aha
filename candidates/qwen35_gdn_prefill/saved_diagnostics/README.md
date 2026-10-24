# Saved Prep-g and real-input head0/M64/M128 diagnostic checkpoint

This is a sanitized record and CLI-rooted helper adaptation of already completed
private Prep-g, head0/M64, and head0/M128 diagnostics on 2026-10-24. Preparing this
checkpoint did not load native arithmetic, run an owner, access weights, or run RTL.
No original production source, mathematical recipe, policy, or acceptance threshold
is changed here. The original execution remains UNKNOWN and is not continued.

Relocated native child/supervisor: TEMP_NOT_EXECUTED. Stdlib mapping/control/CLI tests
and post-comparison of previously completed M128 artifacts passed. These checks and
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
- TEMP: state after token 63 still has no matching official state oracle. Full
  16-head/full-block execution and acceptance, RTL, hardware cycles, effective MAC
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
and ACKs rehydrated TypedMemory. A single non-production-geometry ChunkOwner terminal
used heads=1, key/value dimensions=128, host_batch=true, cold state, IEEE finite gradual
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

The default is --tokens 64. To prepare M128, append all of these arguments to the
prepare_chunk.py command above; 128 is the only additional supported case:

```sh
--tokens 128 --official-state "$OFFICIAL_STATE_0021_FP32" \
  --official-final-cache "$OFFICIAL_FINAL_CACHE_0043_FP32" \
  --official-manifest "$OFFICIAL_CAPTURE_MANIFEST"
```

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
The comparison applies the existing node thresholds to the selected head0 output;
M128 additionally applies the existing per-element state gate to the final after128
head0 state. It cannot promote all-head, full-block, after64-state, or RTL acceptance.

## Lightweight checks performed for this extension

```sh
python -I -S -B -m unittest discover -s candidates/qwen35_gdn_prefill/saved_diagnostics \
  -p 'test_chunk_cases.py' -v
```

Thirteen stdlib tests passed: fixed 64/128 bounds, default64 preservation, CLI state
requirements, token-strided head0 and contiguous state mapping, extent/cache identity,
exact carry completion/read counts, every-element state tolerance (not aggregate-only),
nonfinite rejection, native-independent CLI help under -I -S -B (plus child import-only), and fail-closed
cleanup admission.
Synthetic comparator fixtures test control flow only, not numerical owner correctness.
Source AST and JSON parse checks passed. A separate adapted comparator run over the
already completed private M128 artifacts reproduced every historical result field,
except its own script hash and comparison duration; all input pins remained stable.
It wrote only a fresh private comparison file. No preparation, candidate, native owner,
model, supervisor execution, or Prep arithmetic was rerun for these checks.
