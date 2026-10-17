# Fresh same-host M128 producer extension

Source/cold candidate only. These files do not authorize a producer, model, full M128, compilation, package installation, acquisition, CI or publication. No numerical result follows from the cold tests.

## Invariants

- Immutable M16 driver SHA256 `068d2bdca403b1209c91a03b8bf89b91d9b7f6f4dcd6431a329473fde0702139`; immutable retained-leader bridge SHA256 `23170d4f016900c074a3a446fe4529f7465060c039cdf2aad27bce6a009c6c49`.
- Original generated paired runner SHA256 `d7bd12077675984ed7cc20e57a55729fd62e66b773008fa631673086a5a87a64`; original `native_forward`, numerical thresholds, storage rounding, comparator and semantic helpers remain exact.
- A new producer interpreter calls original `run_gate(tokens=128, carried=False, threads=4, small_gate=current_job_native16_result, ...)` exactly once. It never concatenates smaller runs and never changes ISA environment variables.
- Existing current-job payload, native recipe libraries and producer runtime are explicit `upstream` records. Readonly arena, 128-row input, native128 outputs and both scalar128 outputs are fresh `current` records.
- Native inventory is 29 stages × two modes × two methods = 116 exports. Each scalar reference has 22 raw output files and 12 independently replayed semantic checks. Sequential exports have 29 stages. FP32 remains diagnostic, with no newly approved tolerance.
- Scalar sources remain original sequential and reduced C++, original strict compiler flags, exact original table/arena identities, one invocation per role with row argument `128` and past `0`. Each scalar directory is created exclusively with mode0700. The table command also uses the exact retained-leader helper.

## Exact job layout

`job_out/m16` is the complete unchanged current-job M16 subchain. New producer output is `job_out/producer128`. The parent owns `job_out/M16_PREREQUISITE.json`, `job_out/M128_CONTEXT.json`, `job_out/VERIFIED_M128_PRODUCER.json` and `job_out/M128_QUALIFICATION.json`.

The selected source root is the original current triggering checkout, before detached M128 composition. The exact private interpreter is `job_out/m16/setup/venv/bin/python`. Producer and verifier use `-I -B`, Python3.12.15, first hosted attempt, current CI environment and the observed host/boot. Optimized mode is rejected for production, but cold contracts are tested under `-O`.

## Parent context

`driver.CONTEXT_KEYS` is authoritative. Fields are:

- `schema=1`, `profile=qwen2-fresh-same-host-m128-context-v1`
- `parent_pid`, `root`, `workspace`, `upstream_workspace`
- `created_ns`, `producer_deadline_ns`, `deadline_ns`, `cleanup_deadline_ns`, `receipt_deadline_ns`
- `attempt_nonce`, `ci={commit,run_id,run_attempt}`, `host`
- `driver_sha256`, `source_lock_sha256`, `python`, `upstream`

Deadlines are exact offsets from one `created_ns`: producer260s, shared work290s, cleanup299s, receipt300s. The producer clips every phase to its fixed260s deadline. The separate owned verifier clips its30s allowance to the same shared290s deadline. These limits are unmeasured and fail closed; they do not reset on reentry. Per-phase native128120s, each compiler10s, arena/table30s, each scalar45s.

`upstream` has exactly `producer_manifest`, `qualification`, `native16_result`, `m16_prerequisite`, `combined_library`. Each metadata/binary pointer is `{path:absolute,sha256}`. `combined_library` contains `receipt` and `binary` pointers. Fixed targets are:

- `m16/setup/producer/PRODUCER_M16.json`
- `m16/setup/QUALIFICATION.json`
- `m16/setup/producer/native16/RESULT.json`
- `M16_PREREQUISITE.json`
- `m16/setup/tiny/build/official_bf16_compile.json`
- `m16/setup/tiny/build/official_bf16_matrix_silu.so`

Before numerical production, `verify_upstream` calls the one shared strict `attention_packed_m128_same_host.prerequisite.verify`, including the original full M16 terminal validator, complete frozen M16 source closure, observed full-child exit/cleanup, same current parent/nonce/CI/host/runtime and identical Public compile receipt/ELF. Its five source/data dependencies are pinned in this source lock. A private exact-source import namespace prevents composed-source cache mixing.

## Producer entry

`driver.produce_m128(root, workspace, end_ns, *, attempt_nonce, ci, context_path, context_sha256)` writes `producer128/PRODUCER_M128.json` exclusively. `end_ns` is the shared290s deadline; actual production clips to context260s.

CLI arguments: `--root`, `--workspace`, `--deadline-ns`, `--attempt-nonce`, `--commit`, `--run-id`, `--run-attempt`, `--context`, `--context-sha256`.

Manifest profile `qwen2-fresh-same-host-m128-producer-v1`, status `COMPLETE_FRESH_M128_REFERENCE_OUTPUTS`. `driver.TOP_KEYS` is authoritative. Native/scalar records use `{root,path,bytes,sha256}`. Exactly two roots are allowed: `current=job_out/producer128` and `upstream=job_out/m16/setup/producer`. `resolve_artifact(workspace, manifest, record)` rehashes a regular single-link file under the selected root and rejects symlinks, traversal and changed bytes.

## Independent parent verification

`verify.verify_handoff(root, workspace, manifest_sha256, *, context, expected_context_sha256, decode_native=False)` is safe for direct exact-file loading. `verify.driver(context['driver_sha256'])` checks driver bytes before executing them. Entry admission must load `verify.py` from the original selected checkout using its independently pinned source hash.

`decode_native=False` performs source/record/shape/original numerical-metadata checks, current-job prerequisite replay, strict scalar receipt/ACK checks and current host/compiler/environment/recipe identity checks. It imports no numerical libraries or `candidates` namespace. Original metadata helper function bodies are preserved with only exact enumerated relative-import rebinding. It grants no fresh numerical acceptance; the parent qualification must bind the already completed array verifier.

The standalone CLI always selects `decode_native=True`. It observes the actual current native runtime, verifies all116 original file hashes/geometry/unique inodes, then replays all M128 arrays with original comparator, verdict, embedding, storage and semantic logic. `replay_original.py` differs from original `validate_small_gate` only in function/diagnostic naming and six token/phase literals16→128. The BF16 storage `>>16` remains unchanged. Scalar arrays/cache files and sequential exports are separately decoded and compared against all12 original semantics.

Verifier CLI arguments: `--root`, `--workspace`, `--context`, `--context-sha256`, `--manifest-sha256`, `--out`. `--out` must equal `job_out/VERIFIED_M128_PRODUCER.json`. There is no CLI flag to skip array replay. `verify.verification_receipt` defines its exact output schema/profile/status. The parent must compare this exact receipt and separately observe both producer and verifier zero exits and complete owned-group cleanup.

Final parent qualification uses profile `qwen2-fresh-same-host-m128-producer-qualified-v1`, status `PASS_FRESH_M128_PRODUCER`, and exact fields `schema,profile,status,attempt_nonce,ci,host_sha256,runtime_identity_sha256,producer_manifest_sha256,producer_source_manifest_sha256,parent_context_sha256,verifier_receipt_sha256,child_pid,child_exit_code,owned_group_cleanup_complete,original_array_gate_revalidated,claims`. This parent qualification is distinct from the verifier receipt's own `source_manifest_sha256` field. All six `driver.CLAIMS` remain false.

## Cold verification

Run tests only in a disposable source copy, because the drift tests deliberately edit and restore that copy's sources. No current/frozen tree should be used as the test target.

`python -I -B <copy>/candidates/qwen2_resident_matrix/portable_official_producer_m128/test_driver.py -v`

`python -I -B <copy>/candidates/qwen2_resident_matrix/portable_official_producer_m128/test_verify.py -v`

Repeat with `-O`. The suites are stdlib-only. They execute tiny Python ownership fixtures and source-only patch reconstruction, never numerical code, model arrays, native libraries or compilers. Passing cold tests establishes control/source contracts only; fresh numerical and timing behavior remain unmeasured.
