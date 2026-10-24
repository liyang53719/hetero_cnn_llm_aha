# Saved Prep-g and real-input head0/M64 diagnostic checkpoint

This is a sanitized record and CLI-rooted helper adaptation of two already completed
private diagnostics on 2026-10-24. Preparing this checkpoint did not execute either
diagnostic, load native arithmetic, run an owner, access weights, or run RTL.
No original production source, mathematical recipe, policy, or acceptance threshold
is changed here. The original execution remains UNKNOWN and is not continued.

Relocated CLI helpers: TEMP_NOT_EXECUTED. Their validation is source-only syntax and
static review; historical numerical PASS does not qualify the adapted launcher or
claim that any relocated helper has executed successfully.

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
- TEMP: state after token 63 has no matching official state oracle. State was produced,
  but not numerically accepted. Full M128/all-head/full-block execution and acceptance,
  RTL, hardware cycles, effective MAC utilization, and hardware QoR remain unvalidated.

`observed_metrics.json` contains small aggregate results, not raw tensor values.
The independent Prep diagnostic preserves the legacy magnitude/floor P7 ExpNegative
plus Softplus7 recipe; the experimental chunk split-ln2 exp does not replace Prep op4/op7.
Decimal exp/log at 70 and 100 digits is a precision-stability diagnostic, not a proof
of correctly rounded transcendental semantics. Counterfactual factor replacements
cannot identify the observed official factors because those factors were not captured.

## Historical chunk scope and resources

The actual input was the first 64 rows of an already saved real Prep result, not zeros,
a generated fixture, a Prep rerun, or an original receipt replay. Diagnostic writes
and ACKs rehydrated TypedMemory. A single non-production-geometry ChunkOwner terminal
used heads=1, key/value dimensions=128, host_batch=true, cold state, IEEE finite gradual
underflow policy, fatal mask 28, finite_mul_tininess_r2, experimental P7 split-ln2 exp,
legacy ascending FP32 cumsum, and row1_streaming matmul. The actual child was blocked
from reference access. Comparison occurred only after supervised completion and cleanup.

Native candidate wall time was 13.013652981026098 seconds; the supervisor took
14.323243860038929 seconds. One CPU, 512 MiB address-space and sampled-RSS caps,
60-second CPU/compute allowance, and 75-second outer budget were used. The child exited
naturally with code 0. The retained leader was reaped only after two complete owned-group
absence scans. All 1,101 historical pins remained stable. These are local software
observations, not end-to-end acceleration or measured hardware utilization.

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
4. For native chunk execution: the selected Python interpreter, NumPy/yaml site tree,
   R2 vector library and metadata, compiler identity, and the original pinned
   `scripts/idma_source_export_20261017/strict_cleanup.py`. Preparation does not compile
   or install them. The runtime pin set is not a complete OS/runtime closure.

`pins.json` records the historical script and plan SHA-256 values for traceability.
The relocated helpers are adaptations, not byte-identical historical executables.
The historical 1,101 count is not the count of a newly prepared relocated plan:
new helper/source snapshot pins differ, and machine-specific Git metadata is not reused.
The selected 912-file runtime digest is compact UTF-8 JSON of sorted
`[relative_posix_path, byte_count, sha256]` rows, excluding `__pycache__` and `.pyc`,
within `numpy`, `numpy.libs`, and `yaml`. No runtime content is bundled.

## Explicit opt-in reproduction

Use private output directories outside the source, runtime, and checkpoint trees.
The original frozen working tree and unrelated processes must not be modified or signaled.
The examples below are templates; variables must resolve to separately supplied inputs.
These commands were not executed to prepare this checkpoint.

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
The comparison only applies the original node thresholds to the head0/M64 output;
it cannot promote full-block, state, or RTL acceptance.
