# First verified fresh same-host M16 assigned-27 milestone

## Cleanup evidence limitation

The original assigned-27 numerical PASS is retained. Historical
owned_group_cleanup_complete=true and owned_groups_cleanup_complete=true are
program/helper-reported flags. They do not independently prove that every
descendant had exited before the cleanup helper returned.

The historical shared helper at
candidates/qwen2_resident_matrix/portable_consumer_qualification/run_ci.py,
SHA-256 `9e498c425f637e53978844a6a21b4ad85899ca72f4bea79f6cd2814d2f956b9e`,
kills the process group and waits for only the direct leader. A new standard-library
timeout fixture, reported by the coordinating task, observed the same-identity
descendant in state R during a scan 0.120–0.458 ms after the timeout exception
returned. A later complete scan confirmed absence by 20.965 ms after return;
these samples do not establish continuous liveness between scans or application
work after SIGKILL. That observation limits the cleanup evidence. It does not retract
the original assigned-27 numerical result or demonstrate that the historical
successful run itself left a descendant alive. This successor preserves the five
original receipts unchanged and corrects only the interpretation of their flags.

Status: `PASS_FRESH_SAME_HOST_M16_ASSIGNED27`. Run 39008436816, attempt 1, commit `bf29c529a74aef4001e5833d1bb022141eb881e3`.
The verified GitHub job 117325592334 completed successfully at 2026-10-17T06:11:41Z.

- Run: https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/39008436816
- Job: https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/39008436816/job/117325592334
- Original artifact ID: 12091514715; ZIP SHA-256: `5169209a5f580e51f0785ef81e6a25577dca47dd7318d17b0e6dd60675741969`

## What the receipt reports

Fresh producer and full same-host M16 succeeded. The full phase was 466.928041294 s;
total elapsed was 534.732416088 s; producer elapsed was about 59.203447365 s.
There are 27 assigned official gates, 28 observed official stages, 17 owner jobs,
21 public completions, 10 capture fields and 16 rows. The additional FP32 stage is
diagnostic. The producer's eight stages and the parent's four later stages all
report PASS, observed/final exit 0, and helper-reported cleanup=true. Full child PID
2421 and the producer/full nonce agree across the safe receipts.

This is assigned-27 acceptance only. Full-29, full-M128, RTL execution, hardware
recipe acceptance, and inherited historical PASS remain false. The source-only
terminal validator explicitly does not authenticate execution on its own.

## Evidence and local verification

The five original JSON files are preserved byte-for-byte. This directory contains
exactly those five files, MANIFEST.json, and this README. The manifest records
original byte hashes, reviewed source bindings, CI identity, scope, and limits.
No raw logs, numerical arrays, weights, private snapshot, native binary or private
qualification receipt is included.

The accompanying archive builder/verifier checks the original ZIP's exact five
members and bytes; strict JSON with duplicate/nonfinite rejection; all safe CI,
nonce, child, exit and reported cleanup fields; and exact stage records. Checking
cleanup fields establishes receipt consistency, not independent all-descendant
exit. It binds the
reported raw 385 and static composed 358 source maps to the pinned source freeze,
checks all 386 frozen raw source bytes, then reconstructs actual-commit
SOURCE_CONTRACT.json using compact sorted JSON plus one newline. Adding its hash
to the static map gives 359 sources and digest `9be8cbe9ae4b7a6ed9b2168c952e2f0a8c86578edce51d2b148bb2cf78513d16`, matching
the full receipt. The expected CHILD_RESULT object can also be reconstructed from
the safe metadata and its reported digest matches.

These checks validate preserved safe receipts and source binding. They do not
rerun or replay the private numerical gates or independently revalidate private
arrays, numerical summary, snapshot bytes, or setup/QUALIFICATION.json. In
particular producer_receipt_sha256 refers to that private qualification receipt,
not producer_summary.json. Matching hashes and internally consistent receipts
are not a new execution or an independent signature of CI provenance.

The full-child timing diagnostic is an aggregate parent RUSAGE_CHILDREN delta:
wall 466.833895599 s, waited-child user CPU about 465.30981 s, system CPU about
1.91907 s. It is diagnostic only and proves no causal speedup, per-operation
breakdown, or performance margin for another run.

## Future M128

This archive is a milestone record, not admission authority for any new job.
Future M128 execution still requires its own current-job same-host full-M16
qualification and same-ELF prerequisite, plus the reviewed M128 admission checks.
No M128, full-29, RTL, or hardware acceptance follows from this archive.

## Reproduce the safe archive check

From the accompanying evidence workspace, run `python3 -B build_verify.py --verify`.
Optional `--actual` and `--source-freeze` arguments locate the unchanged original
artifact directory and pinned source freeze. Run `python3 -B test_build_verify.py`
for source-only rejection tests. The build command is `python3 -B build_verify.py
--build`; it writes only the evidence workspace, never the original inputs or
source freeze. No repository module, model, package installer, native program,
Git command, network request, or CI job is invoked by these commands.
