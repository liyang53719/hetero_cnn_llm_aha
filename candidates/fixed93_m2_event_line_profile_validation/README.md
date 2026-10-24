# M=2 event-line profile: portable source excerpt

This package preserves the exact final R2 source bytes of the retained 0557 diagnostic candidate, plus a privacy-safe account of already completed reviews. It is **not a standalone or complete runtime**, an execution permit, an independent numeric oracle, or an M128/fullblock/RTL pass. The source policy files retain their original `actual_execution_authorized: false` values. No source tests, model invocation, native load, decoder execution, or runtime work was performed for packaging.

## Contents and safe check

`source/` contains 17 unchanged Python files and three original policies: POLICY.json, EVENT_LINE_POLICY.json, and SAMPLING_POLICY.json. The entry/authority/runtime/context/I/O/native/driver/supervision code, current tests and diagnostic controls, sampler/report classifier, both observers, and portable parent decoder/history helpers are present. The prior 0540 full source-test package is not duplicated.

Run `python -B check.py` from this directory. The default check only verifies the finite relative whitelist, file sizes and SHA-256 hashes, UTF-8/private-path policy, compiles Python text in memory, and checks summary consistency. It imports or executes none of the copied sources and writes no bytecode. Its PASS means static excerpt integrity, not behavioral or evidence acceptance.

An optional `--original-source ORIGINAL_SOURCE_DIRECTORY` also reads the original source manifest and copied source files to verify their existing pins. It never runs them. No original machine path is encoded in this package.

`PORTABLE_MANIFEST.json` pins every other file and every exact excerpt against its original relative name. The manifest itself must be pinned by the publication/review record. `SUMMARY.json` distinguishes the sampled 0557 result from the unsampled 0549 result. Review and omitted-evidence hashes are provenance references, not evidence bundled or independently revalidated here.

## Retained 0557 result and sampling limits

The completed review reports 53 post-exit files totaling 6,603,299 bytes; all 33 field/presence/output files and transport match the pinned historical successful run by exact size and SHA-256. Decoded comparisons contain 8,565 Attention records and 2,211 wholeblock records with no semantic differences after the documented opaque-ID treatment. There are 11,011 opaque-ID difference rows and four long-lived mappings. Short-lived alias equivalence is not proven. Raw streams are not byte-identical and no stream, ID payload, array, or physical address is included.

The auxiliary profile reports 1,461 samples, 925 unique stacks, 117 code entries, zero reported overflow/truncation/reentrant-loss counters, and restored inactive sampler state. One observed CPU sample gap exceeds 50 ms. Zero reported loss does **not** prove every physical timer tick was represented. Python recovery frames can absorb delayed/coalesced signals, C/native stacks are absent, and sample fractions are not exact CPU fractions.

A separate retained-profile V2 analysis reports selected leaf counts of audit hooks 453 (190 + 158 + 105 across three functions), Attention `_trace` 396, shared `_dispatch` 262, `WholeblockObservation._observe` 90, and `native_snapshot` 42, out of 1,461 stored samples. These are leaf observations, not exact CPU fractions or every physical tick. The selected function counts must not be confused with broader grouped partitions (which include helper frames), and inclusive counts overlap. The analysis is referenced by hash in SUMMARY.json; its private-path artifact is not included and this package checker does not recompute it.

The profiled main-loop CPU/wall durations are approximately 15.754730907/16.245101329 seconds. They describe this perturbed diagnostic run, not a speed acceptance measurement. The unsampled 0549 run separately reports approximately 14.929663849/15.390011784 seconds, a single historical 9.008963% CPU / 8.947760% wall reduction versus 0526. There is no contemporaneous pair, repeated-run estimate, confidence interval, M128 prediction, or full-duration prediction.

Real existing native initialization and cleanup were reviewed: no fresh native compile or native numeric-state reuse; the retained child exited zero, was reaped, and its group was absent. The cleanup signal occurred after exit observation and before reap, not as a timeout or forced-success result. This statement depends on retained original receipts that are not published here.

## Integrity and auxiliary qualification boundaries

The event-only owner-line policy filters normal non-hook lines within a proven live tick while preserving 14 evidence hooks, six scalar returns, retained call/return/exception/outside-tick paths, scope closure, and the shared dispatcher/other subscribers. It deliberately weakens sampling: transient ownership, matrix-context, locals or metadata restored before a retained event can escape detection. Earlier tick ABI/profile transient limits remain. Successful historical equivalence does not restore the old every-line/every-callback integrity contract. The EVENT_LINE_POLICY sampling flag describes that observer policy, not whether the separate diagnostic wrapper enables SIGPROF.

Auxiliary sampling quality is separate from the main evidence seal: bounded, safely restored but incomplete sampling can be PARTIAL without itself invalidating main evidence. Unsafe or active sampler state, malformed data, invalid caps, or broken accounting still block main evidence. Main seal and semantic checks remain mandatory; profile quality never grants model or fullblock PASS.

The old 0437 actual FAIL remains unchanged. The R1 decoder-blocker claim was a mistaken static inference, later retracted; R1 was not an actual failed run. R2 retained separate auxiliary reporting for clarity, not as a repair of a demonstrated actual failure. No decoder widening or model change is claimed.

## Incomplete runtime and excluded private evidence

Excluded: original SOURCE_MANIFEST/BUDGET/HISTORY and admission documents, raw receipts/logs, raw profiles and summaries, event streams, opaque-ID rows, input/output arrays, ELF/native dependencies, environment paths, prior revision trees, original anchors and codec-pin metadata, full base/model/codec runtime, and any new authority. Generic operating-system paths, synthetic test paths, and the source's authority role label remain unchanged. Missing dependencies are intentional; do not execute the included tests or launchers as though this were a runnable kit.

The result remains synthetic N1 Attention M=2, INCOMPLETE_WHOLEBLOCK, with no independent numeric-oracle acceptance, M128 acceptance, or RTL pass. Expanded4096 matrix bank per issue and SiLU nested17 exp/pre-BF16 multiply domains remain unobserved; no public advance/job/completed/PC or SiLU work is established.
