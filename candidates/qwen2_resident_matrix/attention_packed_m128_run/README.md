# Bounded original Public M128 execution wrapper

Prepared source only. An independent review and a separate root execution gate
are required. The default CLI verifies source contracts and prints a plan; it
never starts a numerical job. No download, build, install, prewarming, reference
production, or CI is implicit. Nothing in the M16 wrapper or origin is edited.

## Exact execution identity

This separate wrapper composes attention_packed_m128_entry from its frozen
ce0b54f6c73eec52736feb22e89b72ef388427b8abce04865a135dff76790a42
pins. Its 344 source inputs and 346 final runtime files are distinct, verified
closures. Final source-map SHA256 (sorted compact JSON plus newline):
f5e1dcdecc406750cd6409e45a97184294ba94d4e61cb9ef67d53641fd912104.
The original clean be00 Git repository is cloned locally with --no-hardlinks,
without a checkout first, and GIT_NO_LAZY_FETCH=1. Only exact composed files
are overlaid. Committed qwen2_block.cpp arithmetic and Git HEAD are verified.
The one isolated child reexecutes -I -B at the same PID into the genuine Git
root, clearing preparation imports without restarting any deadline.

M128 admission uses immutable origin assets, not newly produced or relabeled
M16 references. Its pins SHA256 is
2ac1560ca63e28c49e5c2a2b387c98ed50d476f300489276b84edd0ba33598d7.
The admission receives origin, compile_receipt, compile_origin and the completed
repaired-M16 prerequisite workspace. The latter is an explicitly verified
prerequisite, never an M128 verdict. The original 13 weights, native128 and both
M128 reference methods remain untouched. The strict combined-library verifier
retains its exact source-origin and receipt checks.

## Bounds and process ownership

The one original entry.run call receives rows=128 through the snapshot and
wall_budget=2400. Work ends at 2424 seconds from wrapper start. Cleanup has at
most five seconds and stops by outer_deadline-1, reserving one final second for
the receipt inside the hard 2430-second envelope. Slow composition, admission
or postflight can exhaust work earlier; no budget is extended. A supervising
caller must use TERM at 2424 seconds and KILL at 2430, allowing cleanup reserve.

The dedicated parent owns the child process group continuously. It temporarily
blocks ALRM/TERM/INT across spawn/ownership assignment; the child clears the
inherited mask. Linux subreaping plus PID start times track descendants, and
failure runs bounded TERM/KILL/reap cleanup. The parent timer remains armed
across the child's tiny same-PID exec timer gap. A persistent exclusive attempt
lock is created with O_EXCL semantics (xb). A preexisting workspace is rejected
before ownership, so replay cannot rewrite its lock, receipt or earlier result.
There is one numerical child and one original Public run call per attempt.

## Invocation and immutable sources

Use the original private CPython interpreter, normal optimization level only:

    PYTHON -I -B /path/to/attention_packed_m128_run/launch.py \
      --source-root SOURCE --origin ORIGIN --m16-prerequisite M16_COMPLETED \
      --compile-receipt BUILD_JSON --compile-origin BUILD_SOURCE \
      --workspace FRESH_OUTPUT --python PYTHON --contract-sha256 REVIEWED_SHA256

This command is plan-only. Adding --execute requires the separate root gate.
The reviewed contract binds exact wrapper bytes, support bytes, source pins,
source count/digest and CPython implementation/version/size/hash. All private
paths remain runtime arguments. The source input, origin, completed prerequisite,
compile origin, wrapper and fresh output must remain disjoint as checked.
Environment forwarding is allowlisted; ISA, loader and Python path overrides
fail closed. No existing receipt is rewritten and no previous PASS is inherited.

## Terminal verification and safe failure

The actual private summary has a distinct 16 MiB bounded strict-JSON reader;
control JSON and snapshots remain bounded at 2 MiB. Duplicate keys, nonfinite
numbers, excessive complexity and invalid types fail closed. Returned-vs-disk
comparison uses strict canonical JSON, preserving bool/int/float distinctions.
The same on-disk bytes are hashed and re-read by the terminal validator, child
marker and parent postflight. This accommodates genuine M128 reports exceeding
4 MiB without relaxing control metadata bounds.

The validator preserves the original 28 observed stages, 27 assigned official
gates, diagnostic-only softmax_fp32, all ten causal fields, 15 whole-stage and
six observed-node fixed-arithmetic comparisons, 19 sealed outputs, 21 ordered
public completions and 17 owner jobs. It preserves inclusive thresholds and
truthful auxiliary independent-self-cache failures. Tensor arrays are not read
by terminal validation. Snapshot-map hashing uses sorted indent=2 JSON plus
newline; run-context hashing uses sorted compact JSON plus newline.

A valid child marker is insufficient: the parent must observe clean zero child
exit, verify source/context/snapshot/report identities, and publish a bounded
receipt. The caller must independently observe zero launcher exit. Failure
reports distinguish numerical_run_started from actual_chain_completion_verified;
starting or leaving a partial report does not imply completion. Publication
failure never claims verified completion. Full-29, RTL, hardware-recipe and 90%
useful-wall-MAC acceptance remain false even if the assigned observed gates pass.
All private tensors, assets, observations and full logs remain private. Public
progress contains only fixed phase, ordinal, PID, bounded monotonic elapsed time
and context digest. A phase completion is not numerical acceptance.

## Cold checks

Run unittest for test_launch and test_terminal_validator normally and with -O.
Tests use synthetic metadata and small stdlib control processes. They do not run
Torch, native libraries, original reference producers, weights or numerical jobs.
They cover >4 MiB reports, 16/2 MiB boundaries, strict canonical type equality,
exact source maps and budgets, one call/child, origin-only admission keywords,
cleanup receipt reserve, replay ownership, cancellation and safe failure scope.
Synthetic receipts and source checks are never numerical evidence.
