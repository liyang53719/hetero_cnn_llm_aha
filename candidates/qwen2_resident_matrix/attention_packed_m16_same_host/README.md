# Fresh same-host full M16 entry (source-only candidate)

This is a distinct admission profile: `qwen2-public-pv16-packed-m16-same-host-v1`.
It consumes freshly generated same-host official/native and sequential/reduced M16
references. It never relabels the historical AVX512 producer or imports the old
M16 PASS. This control-optimization successor has not run a full numeric workload or CI job.
Its predecessor on commit 6cc2003 passed the fresh producer and failed at the
unchanged 900-second guard during PC19 Down; the safe evidence is archived under
`reports/execution/QWEN2_SAME_HOST_M16_PC19_TIMEOUT_20261017`.

## Preserved numerical and transaction contract

The source composer starts with the exact reviewed `attention_packed_m16_host_job`
composition. It keeps the four entry/identity import changes and truthful
reference metadata, then applies one exact-hash-guarded control optimization:
`ordinary_edge` obtains `self.ports()` only for job admission, where the value is
used. The immediately following pre-owner reset inspection and post-owner live
reset inspection remain. The full concrete getter closure is observationally
pure; no owner or Host edge, deadline site, numerical call or traffic fence is
removed. The Public21 physical prefix/suffix execution, same owner/services,
ACK/publication and whole-terminal checks, whole-reference fence, exact fixed
arithmetic comparisons, 27 assigned official observed-node gates, and original
operator/block thresholds stay unchanged. The explicit mask remains unobserved;
softmax FP32 remains diagnostic. Passing this entry would not be full29, RTL,
hardware acceptance or evidence of 90% useful-wall MAC utilization.

`terminal_original.py` is byte-for-byte the independently reviewed historical
wholephase validator (SHA256 `2fdabe1135b877fa6b78a1cd8f4b51dd14da316773ec79413ff5edd743683347`).
`check_terminal_scope()` allows only fresh profile, reference provenance booleans,
reference wording and result-status substitutions in its separate fresh version.
The old files and historical attempt directories remain untouched.

## Integration API (requires the separately reviewed parent supervisor)

1. `prepare.compose(destination, git_head=triggering_commit,
   producer_package=reviewed_portable_official_producer_directory)` creates a new
   source overlay and returns its complete hash map. Apply it to a fresh genuine
   Git worktree at that exact triggering commit. The original committed scalar
   C++ must still match Git. The producer source-lock is included without changing
   its hashes. No compiler, native or reference arithmetic runs during composition.
2. In the same CI attempt, use the unchanged qualified consumer worker/control to
   freshly compile the combined Matrix/SiLU ELF and repeat its actual tiny tests.
   Keep that exact build receipt and source-origin tree. Historical tiny results
   and historical ELF hashes are background evidence only.
3. Generate the fresh producer outputs in a private workspace disjoint from the
   composed source tree (neither path may contain the other). Admission rejects
   overlap before loading generated code or writing a manifest. The
   supervisor independently validates all original M16 native gates and exports,
   observes the owned child exit, cleans the retained process group before reap,
   then issues the exact `PASS_FRESH_M16_PRODUCER` qualification receipt defined
   by `admission.validate_qualification`. It binds nonce, CI commit/run/attempt,
   host/runtime/source and producer-manifest hashes, plus the fresh tiny-result
   hash and canonical merged tiny source/generated source-map hash. Only `run_attempt='1'` is
   accepted. Its scope explicitly excludes Public/full29/RTL/hardware acceptance.
4. Start a clean isolated consumer child from the composed genuine worktree.
   Call `entry.configure_backend()` once to set the original 4-thread, 1-interop,
   deterministic Torch settings. Call `admission.seal_manifest(destination,
   producer_workspace=..., producer_manifest_sha256=..., producer_receipt=...,
   producer_receipt_sha256=..., compile_receipt=..., compile_origin=...,
   tiny_workspace=..., tiny_input_contract=...)`.
   This checks current host/runtime, streamed reference hashes and original
   metadata/export checks without decoding native arrays or running a forward.
   The unchanged original strict compiler/ELF verifier checks the actual compile
   origin and identical four-source arithmetic closure in the consumer tree.
   Admission also revalidates the unchanged tiny result schema, every tiny source
   byte, its exact build/source paths, and all three actual tiny interpreter/
   compiler/combined-ELF identities against the current producer observation.
5. Invoke `entry.run(fresh_workspace, manifest=..., manifest_sha256=...,
   run_context=...)` once. The externally supplied context contains exact keys
   `profile,attempt,pid,parent_pid,started,work_deadline,outer_deadline,
   source_manifest_sha256,producer_receipt_sha256,attempt_nonce`.
   Its attempt is exact integer 1; deadlines are the original start+924/start+930,
   with at most 900 numeric seconds. Context must come from an independently
   authenticated parent launch; reading a JSON receipt does not grant authority.
6. Parent authenticates the returned `CHILD_RESULT.json`, the actual owned exit
   and group cleanup. It should publish an assigned27-only result only after
   same-byte terminal validation and final source/input verification succeed.

The child API does not create or supervise its own process group and has no
execute CLI. External SIGTERM/SIGKILL/deadline protection must cover synchronous
Torch, hashing, compiler queries and the actual numerical run. Failed admission,
consumer failure or timeout must preserve diagnostic artifacts and remain FAIL.

## Cold verification

Run from the repository root:

    python -B -m unittest candidates.qwen2_resident_matrix.attention_packed_m16_same_host.test_entry candidates.qwen2_resident_matrix.attention_packed_m16_same_host.test_terminal_validator -q
    python -O -B -m unittest candidates.qwen2_resident_matrix.attention_packed_m16_same_host.test_entry candidates.qwen2_resident_matrix.attention_packed_m16_same_host.test_terminal_validator -q

All fixtures are explicitly synthetic metadata. They do not prove numerical
success. Cold checks cover exact identity/schema rejection, no old reuse,
first-attempt restriction, independent parent context, hash-only producer API,
source/wholephase scope preservation, original inclusive threshold behavior,
FP32 diagnostics, failures, aliases, source drift, ACK and completion counts.
See `RESOURCE_PLAN.json` for historical measurements and proposed reserves.
Fresh-reference setup uses the launcher's shared 900-second outer envelope
(work deadline 890, cleanup deadline 899), including package installation, fresh
tiny checks, the producer, independent original-array verification and the parent
qualification receipt. The separate full-M16 930-second envelope is unchanged.
Per-stage setup caps are ceilings within the shared deadline, not additive
allocations or permission to extend it.

## Control-only evidence limit

`test_control_ports.py` compares the original and candidate wrapper control traces,
including admission ordering, poison, abort, stalls, ACK and completion fences,
and checks the composed runner/observer/source hashes. Synthetic wrapper and
original-driver control profiling do not establish full-run speedup or guarantee
completion inside 900 seconds. Parent phase wall and aggregate reaped-descendant
CPU timings are diagnostic metadata and cannot grant numerical acceptance.
