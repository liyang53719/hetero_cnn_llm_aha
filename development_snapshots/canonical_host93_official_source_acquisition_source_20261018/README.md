# Fixed official Verilator source: preserved acquisition, read-only qualification and future receipt repair

This is a 20-file pure-SOURCE publication candidate. Sixteen executable-source or policy files retain their original exact bytes; four aggregate documents describe scope, dependencies and safety history. No archive, selected source body, original execution receipt/log, machine inventory, local launch argv or review report is included. Publication preparation did not execute this projection or change the repository or original assets.

Suggested repository location:
`development_snapshots/canonical_host93_official_source_acquisition_source_20261018/`

## Layout

- `worker_v1/`: `acquire_official_source.py`, `acquire_base.py`, `SOURCE_PLAN.json`, `FIXED_CORE_MEMBERS.json`, `test_source_cold.py`
- `outer_v1/`: `run_gate.py`, `GATE_PLAN.json`, `test_gate_cold.py`
- `same_asset_readonly_v1/`: `run_readonly.py`, `PLAN.json`, `test_cold.py`
- `receipt600_future_v3/`: `acquire_official_source.py`, `acquire_base.py`, `SOURCE_PLAN.json`, `FIXED_CORE_MEMBERS.json`, `test_source_cold.py`
- Aggregate files: `README.md`, `DEPENDENCIES.json`, `HISTORY.json`, `MANIFEST.json`

Each worker reads three fixed sibling inputs through HERE. Their identical base/policy/member-table copies are intentional: they retain original code bytes and working cold layouts without adding a loader, assembler or altered path policy. The member table is metadata only, not the 473 source bodies.

## Exact repository dependencies

The following already-published files remain at these exact repository-relative paths. They are not duplicated in this bundle. DEPENDENCIES.json supplies their sizes and complete SHA256 pins.

1. `development_snapshots/canonical_runtime_ram_source_20261018/run_behavior.py`
   - Outer preflight reads the fixed raw bytes and projects only require/save/group_state/observe_exit/bounded. It does not execute the complete runner module or its native-test main.
2. `development_snapshots/canonical_runtime_ram_source_20261018/test_runner_cold.py`
   - Outer cold reads the SHA-bound raw bytes and projects only FakeOS. It does not execute that module's top level. Consequently its top-level PROJECT_SOURCE_HASHES.json read is not a dependency of this projection.
3. `candidates/qwen2_resident_matrix/host93_source_recovery/acquisition/acquire.py`
   - Outer preflight and posthash compare this exact file with worker_v1/acquire_base.py. Workers load their fixed sibling copy, but never call the old acquirer's group main/load_plan. Its legacy plans directory is not required here.

Within this bundle, read-only cold also requires the exact `outer_v1/test_gate_cold.py`: it verifies its full size/SHA, then projects Cold.fixture_artifacts only. It never executes the old cold module's top level, so FakeOS is not an additional read-only-cold execution dependency. Read-only config loads the fixed `outer_v1/run_gate.py` definitions and projects one postflight mode expression. It does not run outer main or read outer GATE_PLAN.json. The latter remains necessary for the preserved original outer itself.

GATE_PLAN.json's old worker-manifest digest is an informational provenance pin. No preserved code opens that original MANIFEST.json, so it is not copied. Local execution argv, author logs and review reports are likewise not runtime dependencies.

## Caller-supplied paths and entry policy

Let CHECKOUT mean the existing checkout root containing the three repository dependencies, and BUNDLE mean the directory above. These are caller-supplied paths, never embedded local-machine constants. All Python entry invocations must explicitly use `-I -S -B`; use a reviewed fixed size/SHA same-raw entry envelope when required. No invocation or real execution is authorized by this document.

- Original outer SOURCE-only entry: `outer_v1/run_gate.py` with `--repo CHECKOUT --worker-source BUNDLE/worker_v1`. Omit `--output` and the execution guard. Its cold entry takes the same two arguments.
- Historical worker cold: `worker_v1/test_source_cold.py` takes no extra paths. Preserve its original bytes and invoke only with explicit `-I -S -B` or a separately reviewed safe same-raw envelope. It already checks fixed size/SHA before project compilation, but its isolation-flags check is late. Do not claim it has the new front-loaded check, or describe the historical code as lacking hashes.
- Future receipt600 cold: `receipt600_future_v3/test_source_cold.py` takes no extra paths. Its existing flags check is moved before the first project load; size/SHA checks remain unchanged. Its production worker is identical to receipt600 v2.
- Read-only SOURCE-only entry: `same_asset_readonly_v1/run_readonly.py` with `--gate-source BUNDLE/outer_v1 --worker-source BUNDLE/worker_v1`. Omit actual-asset/output arguments and its execution guard. Read-only cold takes those same two source-directory arguments.
- Actual same-asset read-only verification additionally requires separately retained original assets and failed-review evidence through `--original-attempt`, `--failed-actual-review`, `--output` and its reviewed guard. PLAN.json pins their exact bytes. Those assets/reports are deliberately absent from this pure-SOURCE bundle; the caller must supply them separately if that action is authorized.

The original outer is permanently pinned to worker_v1, including its original strict artifact0600 postflight. Do not pair it with receipt600_future_v3: its fixed worker digest will reject the substitution. No new outer-v3 binding has been created or reviewed. The future producer repair is source preservation only, not a ready authorization for a fresh download.

## Three separate safety facts

1. Original acquisition: FAIL remains preserved. The child returned0 with cleanup and all473 selected Git blobs were present, but SOURCE.json was0644 and the original outer required0600. Original outer exit1 cannot be relabeled PASS.
2. New same-asset read-only qualification: PASS_NEW_READONLY_FIXED473_CONTENT_QUALIFICATION. The new outer exited0, the unchanged old tree and473 members were independently checked, and only the exact pinned SOURCE.json data receipt was allowed0644. This is a new content qualification; it does not reverse the old acquisition failure.
3. Future receipt600 producer: a source-only single-process umask077 repair at the sole terminal writer, with caller umask restored and original exceptions retained. Future_v3 additionally moves only the cold isolation check. No current outer is bound to this producer.

HISTORY.json keeps the two actual verdicts in different records and binds the verified review manifest/summary hashes. The read-only PASS uses main review manifest09bb63269e80967dedf42f43a9fab9b20081f1cdc2ec0b2e163388736996268b and summary446c522731edde388f4a199127b5cc4d6872ba8c3fa362013c79a9fb701b6da2, not merely the smaller saved-record scope audit. Reports themselves are not copied.

Neither content qualification nor this source bundle establishes configure/build/startup/hierarchy/DPI/multi-handle/Host/numerical correctness. Observed archive SHA256 remains replay identity, not independent provenance. Resource limits are reviewed configurations; the historical reviews do not claim independent live CPU/RSS/affinity/rlimit telemetry.

## Path and content hygiene

All16 preserved files are free of workspace/home/tmp paths and local candidate-directory references. Remaining absolute literals are intentional portable syntax or negative fixtures: POSIX separators, `/usr/bin:/bin` in a supervisor projection anchor, `/dev/null` for a refused symlink fixture, `/unused` in fully mocked receipt calls, and traversal/absolute tar paths tested for rejection. They are not retained user-machine paths and are not rewritten.

The publication projection has only static byte-copy, hash, dependency and path checks. Future_v3's separately prepared author tests ran48 tiny mocks normally and48 with `-O`; those results are not a new run of this relocated bundle. Independent publication review and any later authorized validation remain separate.
