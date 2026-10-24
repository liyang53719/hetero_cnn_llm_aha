# Qwen3.5-0.8B L0 cold128 + carried128: source and reproduction recipe

## What is and is not reproduced here

The recorded result is the historical typed-software layer-0 execution plus its separately completed corrected postflight comparison. `summary.json` contains whitelisted metrics and evidence digests. It is not a raw terminal or comparator report. Prep has no assigned tolerance; RTL, Scala equivalence and hardware timing/utilization are not qualified.

This directory publishes an executable **source-integrity verifier**, the exact 111 selected source/header-metadata pins, and parameterized existing entrypoint recipes. It does **not** package the private bounded supervisor, its machine-specific reviewed configuration, qualified runtime, checkpoint, inputs, native libraries or tensor outputs. Consequently this is not a self-contained one-command replay of the historical supervision. The recipes below were source-checked, not rerun as a new numerical job for this publication.

Use a new independent source checkout and new output directories. Re-rooting a reviewed configuration changes its bytes and hash; never reuse a historical plan digest for edited configuration. Preserve earlier failures and frozen evidence. All checkpoint/input/reference data stay local or are generated on demand; none are included here.

## 1. Exact source and metadata identity

Source commit: `1ea9b511fc982b2d928472b0dadd9f794c1c20d8`.
Source tree: `e6af2af0b35b7c12907a1ff0b66dd416f0e90571`.

Keep this result snapshot outside the separately checked-out source tree. The snapshot was published after the source commit. With `SOURCE` identifying that independent checkout and `SNAPSHOT` this directory:

```sh
git -C "$SOURCE" checkout --detach 1ea9b511fc982b2d928472b0dadd9f794c1c20d8
git -C "$SOURCE" rev-parse HEAD
python3 -B "$SNAPSHOT/verify_sources.py" --source-root "$SOURCE"
python3 -B -m unittest discover -s "$SNAPSHOT" -p test_verify_sources.py -v
python3 -B -O -m unittest discover -s "$SNAPSHOT" -p test_verify_sources.py -v
```

The verifier pins `SOURCE_PINS.json` itself, checks all selected file sizes/SHA-256/Git-blob hashes, and rejects source aliases, traversal, missing files and malformed inventories. It never imports the verified modules or invokes Git/model/native code. Its success means selected bytes only, not HEAD, full repository/runtime closure, numerical acceptance or hardware validation. The Git commands above are separate source-checkout steps.

The inventory includes the existing public tensor-header metadata file, not tensor values, weights or a native binary. No metadata file or other binary is newly uploaded in this batch. The initial actual source subset had 109 files; corrected comparison used an exact-byte replica plus:

- `src/heteronpu/qk_norm256_candidate.py`, SHA-256 `1307cfd77b105fea758e0e434caab35db908739cc8bdfa0c3857306820532f06`.
- `src/heteronpu/rope_bf16_candidate.py`, SHA-256 `fa647411e2c9f33c58c0b8c62d14063ebe249b199a8fcbc2c0d2cc645ff10bfd`.

Both already belong to the pinned source commit. No source algorithm changed to repair that comparator import closure. Full source checkouts contain them; do not repeat an incomplete selected-file export.

## 2. Local payload, fixture and original reference creation

The original source APIs and their hashes are in `SOURCE_PINS.json`:

- `src/heteronpu/pinned_gdn_payload.py`: `selection(root)`, `collect(root, output)` and `load_payload(root, directory)` implement the pinned layer-0 payload contract.
- `candidates/qwen35_gdn_prefill/input_fixture.py`: pinned embedding acquisition/verification and `build_fixture(root, embedding_directory, layer0_directory, output)` create and validate local cold128/carried128 raw hidden inputs.
- `candidates/qwen35_gdn_prefill/native/capture.py`: `run(root, fixture, runtime, output, m)` captures the original reference with `m=128`; `validate_manifest` verifies its metadata and tensors.

For a new run, stage the authorized checkpoint locally using these pinned contracts. The model revision is `2fc06364715b967f1860aea9cf38778875588b17`; the upstream framework revision is `14e738b5d0cc69aa27a95dde272aea41fde44f2f`. Do not substitute generated downstream outputs as actual inputs.

Existing CLI argument shapes, invoked from the independently reviewed source/runtime environment:

```sh
python3 -m candidates.qwen35_gdn_prefill.input_fixture --root "$SOURCE" collect-embedding --output "$EMBEDDING"
python3 -m candidates.qwen35_gdn_prefill.input_fixture --root "$SOURCE" build --embedding "$EMBEDDING" --layer0-payload "$LAYER0" --output "$FIXTURE"
python3 -m candidates.qwen35_gdn_prefill.input_fixture --root "$SOURCE" verify-fixture --fixture "$FIXTURE"
python3 -m candidates.qwen35_gdn_prefill.native.capture --root "$SOURCE" --fixture "$FIXTURE" --runtime "$QUALIFIED_RUNTIME" --output "$REFERENCE" --tokens 128
```

These are underlying fixture/reference entrypoints, not replacements for admission, process ownership, resource limits or audited runtime checks. This historical actual/postflight batch **did not recapture** the original reference. Future local captures require their own receipts and pins; the listed historical native-manifest digest is not reusable for new bytes.

## 3. Host builds and actual-only API

Build fresh host libraries using `scripts/build_shared_matrix_recipe.py` and `candidates/qwen35_gdn_prefill/chunk/vector.py::build_library(directory, arithmetic_backend=FINITE_MUL_UF_BACKEND)`. The historical Vector16 build used that existing API with `FINITE_MUL_UF_BACKEND` (`finite_mul_tininess_r2`), which selects the pinned C++ source `candidates/qwen35_uf_predicate_r2/vector16_tininess.cpp`. Matrix flags are `-shared -fPIC -O2 -ffp-contract=off -fno-fast-math`; Vector flags are `-std=c++17 -O2 -shared -fPIC -fno-fast-math -ffp-contract=off -frounding-math`. Preserve genuine source-root and library-receipt binding. Equal library hashes alone do not authorize reusing a receipt tied to a different source root.

Use Python 3.12, an explicitly admitted NumPy/runtime site, one CPU, and single-thread BLAS/OpenMP. The historical actual wrapper used `-I -S -B`, offline model settings, a 2 GiB address-space/sampled-RSS envelope, and unchanged guard/cleanup code. The total workflow clock was 12600 seconds; requested actual maximum was 12000 seconds, with original owner-abort drain reserve 60 seconds and maximum 7200 seconds per window. Effective budget is derived from the remaining **original** clock, not a reset clock. A new supervised run must define its own frozen input, resource and acceptance plan under the standing project-maintenance authorization.

The actual numerical entrypoint was the existing Python API, with these reviewed keyword arguments:

```python
from candidates.qwen35_gdn_prefill import full_driver

result = full_driver.run(
    fixture, output,
    rows=128,
    budget_seconds=effective_budget,
    window_budget_seconds=7200,
    vector_library=selected_vector_library,
    vector_exception_policy='ieee_rne_finite_gradual_underflow',
    vector_arithmetic_backend='finite_mul_tininess_r2',
    projection_policy='gdn_pair_k512_independent_fp32_sum',
    chunk_exp_policy='experimental_equal_heads_chunk_candidate_p7_split_ln2_gradual_underflow_v1',
    progress_interval_seconds=30,
    progress=read_only_progress,
    observe=read_only_terminal,
)
```

This is an API recipe, not a standalone launcher. The named inputs, remaining-budget calculation and read-only callbacks must be supplied by the separately reviewed supervisor. The current `full_driver.py` CLI does not expose `window_budget_seconds`; do not replace this API call with a superficially similar CLI invocation that changes window admission.

RMS policy is `torch210_cpu_default1024`; chunk cumsum is `legacy_ascending_fp32`, chunk matmul is `row1_streaming`, Vector fatal mask is 28. Experimental exp is not a correctly-rounded or Torch-bitexact claim. Carried128 consumes preceding actual committed history/FP32 state, never reference outputs. References were unavailable to the actual-only child.

## 4. Separate comparison and finalization

After owned-process cleanup and independent actual-terminal review, use the original comparator:

```python
from candidates.qwen35_gdn_prefill import full_compare

comparison = full_compare.compare_run(
    actual_directory, native_manifest, fixture,
    comparison_output, root=complete_comparator_source_root,
)
```

The historical reference runtime was Torch 2.10.0+cpu, DEFAULT CPU capability, single-thread/inter-op deterministic inference, autocast false and highest FP32 matmul precision. The unchanged comparator validates all 23583 frozen runtime records twice. Its original full-shape Conv reference fallback remains; there was no new reference capture or actual rerun. Corrected comparison received an independently frozen exact-source replica with the two missing modules, not an edit to the already-completed actual root.

Keep original gates: ordinary BF16 node max/mean absolute error <=0.03125/0.005; final output <=0.05/0.01; same-actual-input Conv/SiLU <=1 BF16 ULP; every FP32 state element `abs(error) <= 1e-4 + 1e-4*abs(reference)`. The finite-BF16 comparison includes subnormals and treats signed zero as numerically equal; nonfinite values are rejected. Prep is unassigned and must remain null, not PASS.

Comparison work/stage limits were 300/330 seconds, clipped by the original workflow clock. Postflight must verify actual and comparator cleanup, source/native/input/reference/runtime pins and the unchanged original cutoff before accepting a result. The first import/setup failure remains recorded. The raw actual receipt remains `ACTUAL_COMPLETE_UNCOMPARED` with `native_acceptance=false`; the separate corrected comparator and finalization establish the scoped numerical result. Private supervisor/configuration replay is not packaged or claimed by this snapshot.
