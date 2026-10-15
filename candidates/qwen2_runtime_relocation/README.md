# Fixed Qwen2 runtime relocation

This small adapter changes exactly one in-memory value:
`capture_environment.PYTHONPATH`, from checkout
`hetero_recovery_20261013T1036` to `hetero_recovery_20261014T2131`.
Both absolute prefixes are code constants. Other paths, environment values,
native file names, sizes/hashes, runtime requirements, AST records and reference
expectations remain exactly those of the hash-pinned original QKV/full29 source.
The original files and receipts are never changed. There is no arbitrary root,
runtime path, expected hash, package version, model execution or capture option.

## Functions

- `load_original('qkv'|'full29')` verifies and reads only the original pins,
  recipe and capture source files. It does not read ignored work or import them.
- `relocate_runtime(original_pins, family=...)` validates the complete original
  pins, creates a separate copy with the one fixed environment change, and checks
  all six native files by streamed full length/SHA256 before returning that copy.
- `check_native(relocated_pins, family=...)` rejects every other change and checks
  all six files again. Its records use the actual current absolute paths.
- `initialize_runtime(family)` is a separate fresh-process metadata probe. It
  verifies package/native import origins, actual versions/build/AVX512/thread
  settings, and native identities before/after. It executes no model or tensor
  capture. Do not call it in a process that will later need fresh capture imports.

## Existing arithmetic integration

For a new reviewed full29 wrapper, obtain the untouched original pins and call
`relocate_runtime(original_pins, family='full29')` before numerical import.
Pass the returned copy to the unchanged original
`capture(root, pins, out, stage=..., recipe=new_recipe, capability_fd=...)`.
The original capture already accepts a recipe object, so its arithmetic and all
38 model / 14 activation AST nodes need no copy or edit.

The new recipe's `load_pins()` must expose that explicitly relocated copy;
its source/boundary checks must bind both the original pins/source identities and
this adapter, and call `check_native()` before/after. Its environment must use
the actual returned `capture_environment`. It must keep its fresh-input,
source-review, capability, one-use GO, resource guard and receipt checks.
Original source/freeze functions that compare against the old complete pins must
receive the untouched original pins; a mapped copy is not an old pin file.
New receipts must disclose the old/new PYTHONPATH and real current paths.

This adapter does not make the old guard/capability accept a new wrapper or
replace its lifecycle. Full29's original capture imports `lifecycle` at call
time; the new wrapper must bind its reviewed lifecycle implementation explicitly.
For QKV the existing capture uses module-global `R` instead of the full29 recipe
parameter; its new wrapper must bind a reviewed recipe interface explicitly.
No old validation function is silently monkeypatched by this adapter, and no
old metadata or approval is manufactured or uploaded.

## Checks

Cold defaults read source metadata only:

    python -B -S candidates/qwen2_runtime_relocation/runtime.py
    python -B -S candidates/qwen2_runtime_relocation/test_runtime.py
    python -B -S -O candidates/qwen2_runtime_relocation/test_runtime.py

The real metadata-only initialization uses the actual new environment:

    env -u ATEN_CPU_CAPABILITY PYTHONPATH="$PWD/work/runtime_recovery/site-packages" PYTHONNOUSERSITE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1 python -B -S candidates/qwen2_runtime_relocation/runtime.py --family full29 --initialize

Successful initialization covers the six key native files and current import
metadata, not complete historical runtime equivalence or numerical acceptance.
Actual raw input loading and reference capture remain work for the owner wrapper.
