# Host93 CI recovery: original FAIL; build-only diagnostic SOURCE reviewed; actual PENDING

## Current diagnostic checkpoint (2026-10-19)

Original Actions run 39185138343 remains FAIL. Thirteen prerequisite phases had
EXIT0_CLEANED; fresh_make then failed after 47.995942 seconds. Its private native
receipt/log were not available in the safe artifact, so native return code,
signal, timeout, resource usage and cleanup outcome are unknown. The previous
initialized cleanup false was not an observed cleanup failure. No compiler,
resource or sampler root cause is established.

The isolated v2 successor fixes the two finite support findings: a preparation
refusal cannot consume an old receipt, and diagnostic projection cannot cross
the original phase deadline and return success. Independent SOURCE review is complete.
The reviewer independently passed the coordinator 63+63, original support
41+41 and finite support regressions 7+7. These are SOURCE/mocked checks,
not actual CI evidence. The
new diagnostic job has not executed. Its explicit build-diagnostic mode stops
after the same 14 acquisition, existing-tool probe and build phases. It records
finite original terminal/usage observations even on failure, plus recognized,
allowlisted merged compiler-log diagnostics. It does not execute the new
backend, derived model tiny, Host generation, or numerical workloads.

Only an independently reviewed, bounded one-shot workflow push may run this
new diagnostic. The original Host workflow is not retried. Budgets and fixed
sources/patch remain unchanged. Exact v2 three-JSON validation gates upload.
Unknown measurements remain null; final reap signal and original waitid/cleanup
kill events are separate. The actual make log acceptance remains 1 MiB; the
coordinator's 4 MiB value is only its maximum permitted cap.

SOURCE verdict: SOURCE_GO_SINGLE_BOUNDED_CI_BUILD_DIAGNOSTIC_ONLY.
Review manifest SHA256 55cca6e9bc7a56e28b017d152188a8ba983de30dfad2e2b087d0acb3209fbe37; summary SHA256 cc00d4be3e225a45e951c6ff50217731128c3a519da46d6c18d16f1e36843245.
Diagnostic actual: NOT_EXECUTED.

## Historical first-job SOURCE checkpoint


This checkpoint contains the complete fixed one-job source sequence. Preparation has run only source checks and synthetic Python tests. Independent whole-job source review is SOURCE_GO_SINGLE_BOUNDED_CI_HOST_RESET_LAUNCH_ONLY (review manifest SHA256 e5e7c995825cb34aceee1f5c67e4d10d43177b286519651a344b9418e82cbc84; summary SHA256 6f9aaba2f134dea2833c612b6bb6bd2c5345578407040c64b48eff484e814b58). No actual acquisition, fresh tool build, Host generation, C++ compilation or reset/launch from this new CI job has occurred at this checkpoint.

The sequence has 32 bounded child phases: fixed official source acquisition, ten existing-tool probes, one fresh patched Verilator build, the derived tiny qualification, fresh Host93 emission, iDMA319 extraction, retained13 assembly, four configuration files, and Host C++ generation/compilation/reset-launch. The initialization patch is the exact published one-line derived source change applied to the fixed official source before the single build. No missing local binary or prior local actual qualification is inherited.

The workflow has one shared 6600-second job wall. Its first step establishes the common clock before checkout and the fixed iDMA download. The coordinator receives start+6480, leaving 120 seconds for evidence checking and upload. Stage maxima can be cut short by that common deadline; completion is not guaranteed. No automatic retry or second workflow attempt is admitted.

The only intended Host runtime observation is reset followed by exactly one launch handshake, then no further evaluation calls. Eight generated chandle storage declarations are static evidence only. No live eight-handle claim, RAM replay, loaded weights, N0 numerical output or full-block numerical pass is made.

Only three strictly validated JSON files may be uploaded: summary.json, source_hashes.json and stage_exits.json. READY_REQUIRES_ACTIONS_EXIT0 is nonterminal prepared evidence and requires the original Actions execution step exit0. A failed stage or failed job cannot be made successful by writing or uploading a summary. Native logs, signed URLs, tokens, archives, RTL, C++ outputs, ELF files, system inventories, weights and tensors remain private and must not be uploaded or committed.

The fixed iDMA downloader admits only artifact 12099239717 and its exact 9,926,876-byte SHA256 identity. Its short-lived job token is used only for the exact API request; the subsequent signed HTTPS request carries no application Authorization header. Existing platform proxy/CA settings are preserved only where acquisition needs them, without recording their values. Native tool environments remain finite and clean.

On 2026-10-19 at 00:38 UTC, the working environment was observed to have reverted to an older snapshot. Published source and historical safe results through commit 18e757084e4812fe2496ba8321438a468e17b646 remained recoverable. The newer local tool binaries, micro artifacts and unpublished Host recovery candidates were unavailable. The present CI source has new identities and does not turn those missing assets into current evidence.

## Temporary-data policy

Small source checkpoints must be pushed promptly and identify PASS scope, TEMP_SOURCE, or FAIL. Check temporary tracked files hourly. Daily cleanup may remove only confirmed unnecessary tracked temporary data recoverable from Git history, using a normal deletion commit without rewriting history. Preserve reproduction source, pins, hashes and safe result summaries. Do not delete untracked unique files, active work or sole evidence. No deletion was performed in this checkpoint.
