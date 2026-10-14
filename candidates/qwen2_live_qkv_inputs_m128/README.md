# Independent Qwen2 M128 QKV input recipe

Source-only sibling of the unchanged M16 package. Default `NOT_EXECUTED` is a
stdlib source/metadata check, never numerical or hardware acceptance.

## Exact scope

Qwen/Qwen2-1.5B-Instruct revision
`ba1cf1846d7df0a0591d6c00649f57e798519da8`, layer 0, batch 1, exactly 128 true
embedding rows and token/position IDs 0..127, no past, direct gamma, epsilon 1e-6.
The eight original BF16 ranges total 7,085,056 bytes. The existing embedding range
contains 256 rows; no additional range/download is needed. `x` consumes its first
128 rows by exact BF16-word widening. No repetition, interpolation or padding is
used. Q/K/V weights retain the exact output-major to input-major word transpose.

Nine input roles total 7,616,512 bytes. RoPE remains physical `[2,1024,64]`, with
raw FP32 cos/sin positions 0..127 and zero positions 128..1023. It is generated
using the same pinned ordinary-C scalar source/strict flags and full-table hash.
The first/second planes and physical 1024-position stride are fixed.

The posthoc reference executes the same 15 individually hash-pinned official AST
nodes. It never invokes full Attention.forward, a full layer, QK attention,
softmax, MLP or RTL. Nine reference exports total 3,670,016 bytes, native BF16
exactly widened to FP32. The six numeric producer nodes are n0/qr/q/kr/k/v
(2,752,512 bytes); x/cos/sin are input/table cross-checks. Q/K canonical files are
head-major `[1,H,128,128]`. The only comparison mapping is
`transpose(0,2,1,3).reshape(1,128,H*128)`, with separate frozen token-major hashes.
Layout is never selected by smaller error. Cache length is 256; the original
config is 32768. Only positions 0..127 are covered, without full-configuration
or historical runtime equivalence claims. References are never owner inputs.

## Two-phase reference freeze

An explicitly selected `bootstrap-capture` operates only with unfrozen bootstrap
pins and writes `BOOTSTRAP_REFERENCE.json`, status
`BOOTSTRAP_UNACCEPTED_NO_NUMERICAL_VERDICT`. There is no `REFERENCE.json`, no
acceptance, and no automatic pin update. Capture/audit/default final check reject
unfrozen or placeholder references. Independent source/byte review precedes the
source-only freeze of all nine new M128 hashes plus fixed-layout hashes. A fresh
acquire/materialize/capture/audit identity must then reproduce the fixed pins.
Frozen pins refuse bootstrap mode. The final pin file records the bootstrap
manifest hash; neither old M16 reference hashes nor old PASS claims are reused.

## Cold checks

From the repository root, Python 3.12:

```sh
python -B -S candidates/qwen2_live_qkv_inputs_m128/recipe.py
python -B -S -O candidates/qwen2_live_qkv_inputs_m128/recipe.py
python -B -S -m unittest discover -s candidates/qwen2_live_qkv_inputs_m128/tests -v
python -B -S -O -m unittest discover -s candidates/qwen2_live_qkv_inputs_m128/tests -v
```

No Torch, NumPy, Transformers, raw data, ignored-work reads, network, compilation,
subprocess, or write occurs in the default path. Audit-hook cold tests enforce
these restrictions in normal and optimized Python. Tests use ephemeral synthetic
address words and metadata; no tensor corpus is published. Runtime guards use
explicit exceptions, not removable assert statements.

## Explicit reconstruction

All output directories must be absent and exactly
`work/qwen2_live_qkv_inputs_m128/<run-id>/<stage-id>`. Symlinks, traversal,
absolute/aliased paths, overlap and already-existing outputs are rejected. Every
file is exclusively created. No resume/force mode exists. Partial failed outputs
must never be accepted; select a distinct identity for an authorized retry.

The exact original raw subset/receipts are verified before copying. Original HTTP
acquisition timestamps remain unchanged, labelled `verified_frozen_copy`.
Arbitrary caches and M16 materialized/reference directories are not importable.

```sh
python -B -S candidates/qwen2_live_qkv_inputs_m128/recipe.py --action acquire --execute --reuse-frozen --out work/qwen2_live_qkv_inputs_m128/run01/raw
python -B -S candidates/qwen2_live_qkv_inputs_m128/recipe.py --action materialize --execute --subset work/qwen2_live_qkv_inputs_m128/run01/raw --out work/qwen2_live_qkv_inputs_m128/run01/inputs
```

A future explicitly authorized network reconstruction may instead use `--download`
for the same eight pinned official HTTP206 ranges. It cannot fetch arbitrary URLs,
ignore ranges or fetch the full checkpoint. No network acquisition was needed here.
Whole-checkpoint SHA verification is not claimed.

Capture must use a fresh Python process with the already available pinned runtime.
No installer or automatic download is provided. For this checkout:

```sh
export PYTHONPATH="$PWD/work/runtime_recovery/site-packages"
export PYTHONNOUSERSITE=1
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1
python -B candidates/qwen2_live_qkv_inputs_m128/recipe.py --action capture --execute --subset work/qwen2_live_qkv_inputs_m128/run01/raw --inputs work/qwen2_live_qkv_inputs_m128/run01/inputs --out work/qwen2_live_qkv_inputs_m128/run01/reference
python -B -S candidates/qwen2_live_qkv_inputs_m128/recipe.py --action audit --execute --subset work/qwen2_live_qkv_inputs_m128/run01/raw --inputs work/qwen2_live_qkv_inputs_m128/run01/inputs --reference work/qwen2_live_qkv_inputs_m128/run01/reference --out work/qwen2_live_qkv_inputs_m128/run01/audit
```

Required: Python 3.12, NumPy 2.3.5, Torch 2.10.0+cpu commit
`449b1768410104d3ed79d3bcfe4ba1d65c7f22c0`, AVX512, Torch threads 4/interop 1,
deterministic algorithms, no ATEN_CPU_CAPABILITY override. Python, Torch _C,
NumPy multiarray and three Torch native libraries have frozen complete byte/hash
identities, verified before imports and after capture. Compiler/interpreter,
source/recipe files and every existing input-stage file are hashed before/after
execution; drift prevents writing the completed manifest. Compiler flags,
generated C/shared-object hashes, runtime environment/affinity and cross-manifest
bindings are checked. Capture environment is independently pinned; a metadata reader
may use its own import environment without weakening the recorded capture identity.
Audit imports no numeric package and does not execute the
model. It verifies current native file identities against fixed pins.

`verify_reference_metadata(root,pins,subset,inputs,reference,subset_sha,inputs_sha)`
returns validated metadata without reading reference tensor files. This supports
prelaunch admission; numeric consumers must delay `check_records` reference reads
until their own outputs are sealed. Existing read_subset/read_inputs signatures
are preserved. Execution identity covers recipe.py/capture.py/pins.json only;
README, cold tests and summaries cannot silently change the numerical producer.

Only Python source, this README, allowlist `.gitignore`, pins and concise summaries
belong in Git. Raw weights, reference/input arrays, generated C/ELF/shared objects,
runtime/build logs and detailed execution receipts remain under ignored work/.
This recipe does not authorize staging, pushing or numerical/RTL acceptance.

## Recorded local validation

`VALIDATION_SUMMARY.json` records the independently reviewed, frozen M128
reproduction at `work/qwen2_live_qkv_inputs_m128/frozen01`: fresh native preflight,
verified raw copy, materialization, official AST capture and independent audit,
all successful with persisted source/input/tool before/after receipts. All nine
new references match the previously frozen hashes. Twenty-two additional actual
byte/path mutations were rejected without touching the sealed artifacts or
executing a numeric consumer. `COLD_TEST_SUMMARY.json` records 55 normal and 55
optimized tests, 477 metadata rejection verdicts per run, exact source/test
snapshots, and both default `NOT_EXECUTED` checks. This verifies reconstruction
and admission gates only. Numeric model acceptance is a separate consumer task.
