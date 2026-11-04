# Selected original runtime dependency contract

`FULL_READY_SELECTED_DEPENDENCIES_V1` projects original dependencies using the exact bound execution policy. It does not modify the registered five profiles, original installers, wrappers, installation receipts, numerical algorithms, CPU rules, or qualification requirements. Outer cloud admission must independently approve the selected FULL profile list and budget.

## Inventory input

Selected reuse uses `PINNED_EXISTING_SELECTED_RUNTIME_BYTES_V1`. It has the same fields as the legacy three-runtime inventory plus `execution_policy`; its existing scope remains `EXISTING_BYTES_ONLY_REVALIDATE_EVERY_EXECUTOR`. Entries must be exactly the required runtime keys. The archives must be exactly their original locked filename/size/SHA256 union, with no missing, duplicate, changed, or unrelated entries. Existing byte trees, original wrappers, sidecars, installation receipt pins, and current interpreter are still verified. No P0 installed root, P0 smoke import, or P0 AVX512 observation is needed when profile 0 is absent.

Original archive metadata totals, without download:

- Profile 0: 26 files, 238463458 bytes.
- Profile 1 or 2: 39 files, 259895288 bytes.
- Profile 3 or 4: 39 files, 259161043 bytes.
- Profiles 1, 2, 3, 4: 40 files, 287899273 bytes.
- All five selected: 53 files, 305867713 bytes.

The unmodified default FULL and legacy DEFER archive contract remains the original 53-file, 305867713-byte union. Their existing schema names remain unchanged.

## Versioned outputs

Selected archive output schema is `SELECTED_ORIGINAL_RUNTIME_ARCHIVE_UNION_V1`, with the exact `execution_policy`. Scope is `SELECTED_ORIGINAL_ARCHIVES_ONLY_NO_INSTALL_V1` for acquisition or `READ_EXISTING_SELECTED_PINNED_ARCHIVES_NO_INSTALL_V1` for reuse.

Selected fresh-install metadata uses:

- `FRESH_JOB_SELECTED_RUNTIME_INSTALL_BINDING_V1`
- `FRESH_JOB_SELECTED_RUNTIME_RECEIPTS_V1`
- `FRESH_SELECTED_RUNTIME_INSTALL_RESULT_V1`
- `SHARED_SELECTED_RUNTIME_OWNER_FRESH_JOB_V1`

Selected runtime reuse uses:

- `FRESH_SELECTED_RUNTIME_IMPORT_VALIDATION_V1`
- `IMPORTED_SELECTED_RUNTIME_OWNER_CLOUD_V1`

Existing output filenames remain unchanged. All generated phase bindings carry `execution_policy`; selected results bind it too. The registered five-to-three mapping is descriptive only: both fresh and imported owners reject any consumer profile absent from the exact selection, including an unselected sibling sharing the same runtime.

Selected fresh owner bindings additionally carry `source_dir` for rechecking the archive union against the original pinned metadata. `runtime_dependencies.py` and `profile_policy.py` must both be explicitly source-pinned for selected actions. All existing resource, ownership, deadline, EOF, cleanup, source closure, and no-qualification-transfer checks remain.

## Test boundary

Tests use original archive metadata and small synthetic files, plus fake subprocess/supervisor results. They do not acquire archives, install packages, execute original runtime wrappers, run numerical references or DUTs, or establish runtime/numerical PASS.
