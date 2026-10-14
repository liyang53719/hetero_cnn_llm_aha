# Qwen2 M128 five-tail-input recipe

Input reconstruction only. This package never executes Matrix, Scalar, an
upstream forward, a numerical model, or RTL. Default status is `NOT_EXECUTED`.
No historical full manifest or PASS is inherited.

## Exact source and storage contract

Qwen/Qwen2-1.5B-Instruct, immutable checkpoint revision
`ba1cf1846d7df0a0591d6c00649f57e798519da8`, layer 0. The original safetensors
header and payload pins independently fix tensor names, shapes, dtype, absolute
ranges, 14 contiguous segment hashes and five whole-tensor hashes. The already
acquired raw subset is 87,297,024 bytes. The original immutable acquisition
manifest and actual HTTP206 records are verified, including their original UTC
timestamps. No requests, downloads, installs, cache searches or old loaders occur.
The full-checkpoint SHA is not verified.

Only these five `<role>.bin` files are written, totaling 87,300,096 bytes:

| Role | Original BF16 shape [output,input] | Physical shape | Element strides | Byte strides | Stored type | Bytes |
|---|---|---|---|---|---|---|
| wo | [1536,1536] | [1536,1536] | [1536,1] | [3072,2] | BF16 little-endian words | 4,718,592 |
| wg | [8960,1536] | [1536,8960] | [8960,1] | [17920,2] | BF16 little-endian words | 27,525,120 |
| wu | [8960,1536] | [1536,8960] | [8960,1] | [17920,2] | BF16 little-endian words | 27,525,120 |
| wd | [1536,8960] | [8960,1536] | [1536,1] | [3072,2] | BF16 little-endian words | 27,525,120 |
| gamma1 | [1536] | [1,1536] | [1536,1] | [6144,4] | FP32 little-endian | 6,144 |

All four matrices transpose actual 16-bit words from output-major to contiguous
input-major storage. The square wo matrix must also transpose. No matrix is
widened. gamma1 alone uses exact `uint32 = uint16 << 16` storage widening,
with no floating-point arithmetic, rounding, or `1 + weight`: Qwen2 uses direct
gamma. A scalar vector and physical rank-two `[1,1536]` row contain identical
contiguous bytes. Descriptor shape4 and stride3 are explicit in `pins.json`.

The public21 fixture uses descriptor dtype 5 for weights and dtype 7 for gamma1.
Original physical addresses and FP32-sized weight reservations remain intact;
the unused upper halves remain guard space and are not materialized or inputs.
The fixed M128 metadata has maxTokens=1024 address capacity; neither 1024-token
execution nor full-block execution is claimed. No command/descriptor table,
activation, saved intermediate, oracle, cache, synthetic weight, or guard array
is written by this recipe.

## Source correspondence and bounded dependencies

The byte producer reuses the exact `transpose_words` and `widen_bf16` function
ASTs from the pinned current QKV M128 recipe. It does not import that module or
its dependencies. The original public packer's allocation prefix and stride
assignments are evaluated as metadata only. The unrelated `out.exists()` guard
is excluded, and all descriptor encoding/file-writing nodes after `records=[]`
are excluded. Full files and each selected AST node are pinned. Current fixture,
BF16 descriptor converter and fullgraph loader sources are read/hash-checked
only; none is imported. See `source_correspondence.json`.

CPython 3.12 is required before any AST extraction. No cross-version AST-field
normalization is performed. No NumPy, Torch, Transformers, compiler, native
extension, ordinary-C math, or Matrix/Scalar model is needed, including for
explicit materialization and audit. Only eight existing source/metadata files
and this source package are dependencies.

## Cold checks

Run from the repository root with CPython 3.12:

```sh
python -B -S candidates/qwen2_live_tail_inputs_m128/recipe.py
python -B -S -O candidates/qwen2_live_tail_inputs_m128/recipe.py
python -B -S -m unittest discover -s candidates/qwen2_live_tail_inputs_m128/tests -v
python -B -S -O -m unittest discover -s candidates/qwen2_live_tail_inputs_m128/tests -v
```

Default checking reads only source and pinned metadata, including the exact
safetensors header; it never reads `work/`, raw tensors, references or outputs,
and never writes. Audit-hook tests enforce file/import/network/write/subprocess
boundaries. Tests use tiny synthetic words and temporary source-only checkouts,
never production weights. Runtime guards use explicit exceptions, not `assert`.

## Explicit materialization and separate readback

The original raw source is fixed at `work/qwen2_tail_ranges_20261014`. This is a
local-only reconstruction recipe, not a fresh download/acquisition facility.
Missing bytes fail closed. Outputs must be new, canonical, non-symlink paths of
the exact form `work/qwen2_live_tail_inputs_m128/<run-id>/<stage-id>`. There is no
force, overwrite or resume mode. Each output file is exclusively created.

```sh
python -B -S candidates/qwen2_live_tail_inputs_m128/recipe.py --action materialize --execute --out work/qwen2_live_tail_inputs_m128/new01/inputs
python -B -S candidates/qwen2_live_tail_inputs_m128/recipe.py --action audit --execute --inputs work/qwen2_live_tail_inputs_m128/new01/inputs --out work/qwen2_live_tail_inputs_m128/new01/audit
```

All source/header/layout/metadata and complete raw/segment hash checks precede
conversion. Exact independent byte-lane correspondence, output dimensions and
all source/input/layout checks finish before the output directory is created.
Source/input before-and-after identities are persisted. Outputs are read back,
and only a completed run receives `INPUTS_READY.json`; a failed partial directory
is never acceptable. Audit requires that seal, current source/raw identities,
all five output hashes, exact metadata and every byte's fixed address mapping.
No reference or numeric tolerance participates in acceptance.

Materialized hashes are observed deterministic transform results rather than
historical output pins. They cannot authorize a different result: the audit
checks every output byte against the original hash-pinned BF16 input mapping.
Changing both an output byte and its reported digest is rejected.

## Local evidence

`COLD_TEST_SUMMARY.json` records actual CPython 3.12.14 normal/optimized runs,
source-only checkout checks, synthetic negative tests and a separately labelled
mock 3.11 version guard. An actual `/usr/bin/python3.13` invocation is separately
recorded as rejected before AST/data execution; no native 3.11 run is claimed.

`VALIDATION_SUMMARY.json` records one fresh materialization with a 60-second
outer timeout and 512-MiB address-space limit: 12.104 seconds and actual peak RSS
217,948 KiB. Separate recipe readback and an independent stdlib array-index audit
check all 43,648,512 source words. Twenty-one real-byte/layout/path negatives
mutate private copies or in-memory copies only; original inputs and sealed
outputs retain their complete before/after identities.

All raw/materialized bytes, copied mutation payloads, detailed receipts, logs
and independent validation scripts remain ignored under `work/`. Only the
allowlisted source, metadata, README and concise summaries belong in Git.
This package is input preparation, not numerical, hardware, or full-layer proof.
