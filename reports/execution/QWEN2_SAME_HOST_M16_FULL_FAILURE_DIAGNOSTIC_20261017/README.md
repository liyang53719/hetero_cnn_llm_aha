# Full-M16 failure-only observation successor

## Actual fourth attempt

Commit `4f9986188bbc7c0eed8b52432be577493e3a7a45`, run `39001176206`, job `117304228583` failed after 1004.057938535 seconds. The fresh producer was qualified after 76.564196213 seconds; its eight owned phases exited zero with complete cleanup. The new worktree, source composition, and admission phases also exited zero. The full-M16 child exited one and was cleaned completely. Full-M16 assigned27 did not pass; M128 was not run.

Artifact `12088928570` has SHA-256 `aefc23d3fa9f4cd766f60f156140a0b10d8685a9cc815cc49599ad3b075ee3f4`. Its four JSON files were checked byte-for-byte against the archive. The original full child log and private numerical summary were not uploaded. The exact inner cause and last completed public PC are therefore unknown. Elapsed time is not proof of a numerical timeout. The retained GitHub job log shows only the outer nonzero-child error.

The recorded post-setup reserves were four CPUs, 15,566,970,880 available memory bytes and 89,115,750,400 available disk bytes. These observations do not establish the cause of failure.

## Narrow successor

Five source files change: the parent, a new failure observer and its cold tests, the acyclic source input contract, and one workflow revision comment. Every one of the 356 static composed execution inputs remains byte-identical, as do the producer, original array verifier, launcher, worker, arithmetic, numerical gates, and owned-process helper. Setup900, numeric900, full outer930 and combined1950 envelopes are unchanged. There is no retry or acceptance relaxation.

After an observed nonzero full-M16 child exit and completed owned-group cleanup, the parent can place a failure-only observation under `summary.json.full_m16_failure_diagnostic`. No additional artifact path or wildcard is used. The observation cannot grant acceptance, even when private child-written status text contains a historical success label.

The parent reads only its fixed `full_m16.log` and existing `full_m16/actual/summary.json` and `full_m16/snapshot/SNAPSHOT.json`. The unchanged traceback parser emits only allowlisted exception classes and pinned relative-source/hash/line frames. The metadata projection emits a fixed status, explicitly reported prefix completion, contiguous successful completion PCs, selected control counters, reset-required, validated dispatch-PC keys, a closed launch-status enum, bounded launch counts and elapsed scalars. Validated dispatch PCs do not prove that those jobs executed. This metadata does not expose a current pending PC, so it cannot identify an exact failing PC by itself.

The projection binds the observed child PID/exit to the parent's journal, the exact parent run-context hash, the complete composed-source map hash, and the private summary/snapshot hashes. It never copies exception messages, source lines, locals, URLs, absolute paths, memory addresses, tensor contents, job objects, raw memory, requests, or failure-capture payloads.

Limits: at most64KiB of log and4MiB each of summary/snapshot are read, without a limit-plus-one read. Source files are individually bounded and rehashed. Extraction has a one-second local budget and is skipped unless at least two seconds remain before the original full receipt deadline; at least one second is reserved. Global expiry is not swallowed or rearmed, and the original parent failure remains authoritative. Missing, malformed, oversized, chained traceback, unknown status, out-of-range or timed-out observations are unavailable rather than inferred. The one-billion tick/backpressure projection caps are diagnostic availability limits, not new execution limits.

Cold tests exercise strict types, bounds, source/context drift, alias rejection, privacy redaction, real stdlib child nonzero exit/cleanup, isolated imports, near-deadline skip, local/global expiry behavior, and original failure-receipt preservation. Source-only preparation and tests do not qualify any numerical execution. Publication needs a complete383-file audit against the actual candidate Git commit and separate root launch approval.
