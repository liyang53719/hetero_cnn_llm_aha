# Same-host M16: source-confirmed PC19 deadline failure

Run [39005243171](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/39005243171), attempt 1, used commit `6cc2003d8f85d881d7cbb5f6263da06ec3a05f39` and ended in failure on 2026-10-17. The four files under `actual/` are byte-for-byte copies of the verified GitHub artifact JSON members. The archive hash, member hashes and source proof are recorded in `ACTUAL_FAILURE_ARCHIVE.json`.

## Established results

- The same-host producer passed in 84.792876 seconds. All eight producer stages exited zero and completed owned-process cleanup.
- Full M16 executed for 900.232086 seconds, completed public PCs 0–18, and had dispatched PC19 Down when it failed. The child exited 1 and owned-process cleanup completed.
- The source-bound traceback terminates at the cumulative monotonic deadline guard in `ffn_public/execute_numeric.py:109`. The unchanged call chain routes this through the original Down driver for PC19. This establishes the inner 900-second budget failure; it is not inferred merely from overall elapsed time.
- The returned/disk writer-byte comparison and whole terminal validator were not reached. Full M16 is not terminal-qualified, and M128 was not started.

## Source and timing comparison

The source-only check reconstructed and rehashed all 356 static executed files and matched the actual 382 input pins to the frozen launch contract. All eight retained traceback frames match those exact source hashes. The check imports no numerical sources and passes in normal and optimized isolated Python modes.

Against the earlier run 39003509172 on commit 46f5766, the only static source changes are the M16 entry writer-byte repair and its test file. The other 354 files, including all hot-path model runners and arithmetic, are identical. That earlier run observed all 21 completions in 643.242548 seconds before failing at its then-incorrect writer boundary. Its prefix took 36.979843 seconds; this run's prefix took 57.501868 seconds.

The retained evidence does not establish the cause of the execution-rate variance. CPU model, host contention and per-phase CPU attribution remain unknown. No timing limit, numerical gate or acceptance claim is relaxed. The earlier 4f99861 failure remains independently undiagnosed.

## Evidence limits

Failure diagnostics are explicitly diagnostic-only and do not authenticate child-origin numerical claims. The producer milestone and observed exit/cleanup records are preserved, while whole-graph terminal qualification remains false. No raw logs, tensor payloads, exception messages or local variables are included. This archive grants no M128 launch authority.
