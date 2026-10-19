# CI build-only failure diagnostics (SOURCE candidate)

This successor addresses the observability gap from Actions run 39185138343.
The original run remains FAIL: 13 phases exited zero with confirmed cleanup,
then `fresh_make` raised after 47.995942 seconds. Its private receipt and merged
native log were not retained publicly. Native exit, signal, timeout cause, CPU,
and cleanup outcome remain unknown. The former initialized cleanup `false` was
not an observation. No particular compiler, resource, or sampler failure is
established.

## Narrow changes

- `ci_support_v3.py` leaves the fixed published WNOWAIT functions and observers
  unchanged. An optional caller-owned dictionary receives a finite numeric
  projection of the self-produced receipt and child-usage observation even
  when `run_phase` raises. Invocation argv/cwd/CPU/AS must match privately.
  The original exception wins over diagnostic failures. Receipt recovery is
  allowed only after this fresh invocation reaches its native-call boundary;
  a preparation refusal cannot read an old output receipt. Diagnostic projection
  remains inside the same phase deadline, checked again before returning. An
  alarm during projection cannot turn into success or extend that deadline.
- `receipt_timed_out` preserves the supervisor classification, which also covers
  its signal handler's `TimeoutError`; it does not independently identify a
  resource limit. `final_reap_signal` is derived only from a negative reaped
  return code. The original unreaped waitid code/status and cleanup kill fields
  are retained separately. A cleanup kill is not labelled a natural signal exit.
- Unknown cleanup is null. True requires spawn/anchor/reap/absent proof. False
  requires a recorded present group. Child user/system values are the observed
  RUSAGE_CHILDREN difference; peak RSS is cumulative in the coordinator process,
  not a phase-specific or instantaneous measurement.
- Only failed `fresh_make` may add sanitized merged compiler-log diagnostics.
  At most the last 1 MiB is read from the fixed private regular `native.log`;
  an incomplete first line is discarded. At most 20 recognized observations and
  8192 canonical bytes are admitted. Paths must be in the fixed public 473-file
  source list; diagnostic prose is replaced by five fixed messages. Unknown,
  non-ASCII/control-bearing, credential-like or arbitrary lines are omitted.
  The public field is `merged_log_tail`, not independent stderr. Empty output
  does not prove the compiler produced no errors. `truncated` covers tail/row caps.
- `toolchain.run(..., stop_after_build=False)` retains its default full behavior.
  Explicit true performs the same 14 acquisition/probe/build phases, original
  build postflights, backend/runtime identities and source/tool rechecks, then
  returns without executing the new backend or derived tiny/Host phases.
- The coordinator adds `--mode build-diagnostic`, requiring no iDMA archive.
  It rejects an archive in this mode and accepts only the exact 14 stage names.
  It may claim `toolchain_build`; all tiny/Host/numeric scopes remain false.

## Budget and evidence

The same supplied absolute job deadline applies. The workflow retains 110
minutes overall, passes its 6480-second work deadline, and reserves time for
verification/upload. The existing fresh make cap remains 3600 total / 3570
work and CPU, one CPU, AS 4 GiB, FSIZE 1 GiB, actual log acceptance 1 MiB (the coordinator permits at most 4 MiB). No retries,
checks disabled, source patch changes, alternate transport, or budget increases.

Exactly three JSON files, combined at most 1 MiB, are uploadable after strict v2
schema verification: summary.json, source_hashes.json, stage_exits.json.
A prepared READY record requires the actual Actions exit zero as well. Failure
reporting never changes the original process exit into success. Original logs,
archives, native code, machine inventories, credentials and tensors stay private.

Execution interface after SOURCE acceptance:

    python3 -I -S -B candidates/host93_ci_recovery/run.py --mode build-diagnostic --repo "$GITHUB_WORKSPACE" --out "$RUNNER_TEMP/host93-build-diagnostic-private" --job-deadline "$HOST93_WORK_DEADLINE" --execute

Evidence-only verification (no native action):

    python3 -I -S -B candidates/host93_ci_recovery/run.py --verify-evidence --out "$RUNNER_TEMP/host93-build-diagnostic-private"

Cold entrypoints from `candidates/host93_ci_recovery`, each repeated with `-O` after `-B`:

    python3 -I -S -B test_run_cold.py
    python3 -I -S -B test_support_v3_cold.py --repo /absolute/project/repository
    python3 -I -S -B test_support_regressions_cold.py
    python3 -I -S -B run_diagnostics_cold.py
    python3 -I -S -B toolchain/test_toolchain_cold.py --repo /absolute/project/repository
    python3 -I -S -B toolchain/test_transport_cold.py

These use fixed size/SHA checks on the same buffers before project compile/exec.
They exercise synthetic fixtures/mocks only. No new acquisition, make, backend,
Host, or CI execution occurred while authoring this candidate.
