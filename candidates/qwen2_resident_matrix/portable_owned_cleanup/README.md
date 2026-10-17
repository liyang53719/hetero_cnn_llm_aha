# Strict owned process-group cleanup

This stdlib-only Linux helper is a separate production successor. It does not modify the historical consumer helper. The importing launcher/producer owns the original stop, process handle, source admission and downstream failure policy.

## Loading and calling

Read and SHA-256-check the source bytes against the caller's source lock. Create a private module namespace and inject `_ADMITTED_SOURCE_SHA256` with the digest of those exact admitted bytes, then `exec(compile(admitted_bytes, source_path, 'exec'), module.__dict__)`. Import without this digest is rejected. A self-read of a pathname is not an execution-buffer binding.

After the caller disables its work timer and protects cleanup signals, call `proof = module.cleanup_owned(owner, original_stop)`, then `module.validate_cleanup_proof(proof, owner=owner, stop=original_stop)`. Only successful validation permits setting `cleanup_complete` or consuming artifacts. Existing owner shape is `{'process': unreaped_Popen, 'identity': {'pid', 'ppid', 'group', 'start'}}`; an initially unset identity may be established only using the retained direct child and strict current metadata. The process must be its own session and process-group leader.

The helper keeps the leader unreaped, verifies identity, sends group SIGKILL within the original stop, and requires two complete scans with no nonleader identity, including Z/X/x. It then reaps only the direct leader and finalizes its alarm before producing the source-bound, parent-owned proof. It never claims to reap grandchildren. Every fresh identity read and full scan is covered by an alarm using the same absolute stop. Scan evidence has cumulative record and byte limits; exceeding either fails cleanup.

## Failure and scope

`CleanupFailure.evidence` retains bounded private diagnostics. Cleanup failure is distinct from a work timeout: retain the first work error and record cleanup failure independently. Failure may reap the direct handle within remaining time or nonblocking, explicitly releasing authority without claiming group disappearance. No signal is allowed after expiry or reap. Incomplete cleanup blocks receipts and next-stage work; it must never be softened into an expected timeout.

Raw observations contain process identities and stay in private diagnostic evidence. Safe job artifacts receive only the separately reviewed bounded projection, never raw proof/scan dictionaries. The helper proves an anchored original-group boundary plus observed member identities, not a historical descendant tree. An unobserved escape predating cleanup is outside that scope. Every independently owned nested group needs its own barrier.

## Verification

`test_strict_cleanup.py` is deterministic and does not spawn processes. Run in normal and optimized isolated modes. `lifecycle_check.py --output <new-directory>` is an explicit separately reviewed stdlib lifecycle check, once each for retained zero exit, nonzero exit and original work timeout. It preserves readiness identities, strict proof, and same-stop post-return observations. Fixture failures are preserved without retries or post-reap group signals. No numerical/model/native/compiler tests are part of this module's cold checks.
