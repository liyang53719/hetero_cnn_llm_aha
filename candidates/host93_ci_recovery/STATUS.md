# Host93 CI recovery: SOURCE reviewed; first CI actual PENDING

This checkpoint contains the complete fixed one-job source sequence. Preparation has run only source checks and synthetic Python tests. Independent whole-job source review is SOURCE_GO_SINGLE_BOUNDED_CI_HOST_RESET_LAUNCH_ONLY (review manifest SHA256 e5e7c995825cb34aceee1f5c67e4d10d43177b286519651a344b9418e82cbc84; summary SHA256 6f9aaba2f134dea2833c612b6bb6bd2c5345578407040c64b48eff484e814b58). No actual acquisition, fresh tool build, Host generation, C++ compilation or reset/launch from this new CI job has occurred at this checkpoint.

The sequence has 32 bounded child phases: fixed official source acquisition, ten existing-tool probes, one fresh patched Verilator build, the derived tiny qualification, fresh Host93 emission, iDMA319 extraction, retained13 assembly, four configuration files, and Host C++ generation/compilation/reset-launch. The initialization patch is the exact published one-line derived source change applied to the fixed official source before the single build. No missing local binary or prior local actual qualification is inherited.

The workflow has one shared 6600-second job wall. Its first step establishes the common clock before checkout and the fixed iDMA download. The coordinator receives start+6480, leaving 120 seconds for evidence checking and upload. Stage maxima can be cut short by that common deadline; completion is not guaranteed. No automatic retry or second workflow attempt is admitted.

The only intended Host runtime observation is reset followed by exactly one launch handshake, then no further evaluation calls. Eight generated chandle storage declarations are static evidence only. No live eight-handle claim, RAM replay, loaded weights, N0 numerical output or full-block numerical pass is made.

Only three strictly validated JSON files may be uploaded: summary.json, source_hashes.json and stage_exits.json. READY_REQUIRES_ACTIONS_EXIT0 is nonterminal prepared evidence and requires the original Actions execution step exit0. A failed stage or failed job cannot be made successful by writing or uploading a summary. Native logs, signed URLs, tokens, archives, RTL, C++ outputs, ELF files, system inventories, weights and tensors remain private and must not be uploaded or committed.

The fixed iDMA downloader admits only artifact 12099239717 and its exact 9,926,876-byte SHA256 identity. Its short-lived job token is used only for the exact API request; the subsequent signed HTTPS request carries no application Authorization header. Existing platform proxy/CA settings are preserved only where acquisition needs them, without recording their values. Native tool environments remain finite and clean.

On 2026-10-19 at 00:38 UTC, the working environment was observed to have reverted to an older snapshot. Published source and historical safe results through commit 18e757084e4812fe2496ba8321438a468e17b646 remained recoverable. The newer local tool binaries, micro artifacts and unpublished Host recovery candidates were unavailable. The present CI source has new identities and does not turn those missing assets into current evidence.

## Temporary-data policy

Small source checkpoints must be pushed promptly and identify PASS scope, TEMP_SOURCE, or FAIL. Check temporary tracked files hourly. Daily cleanup may remove only confirmed unnecessary tracked temporary data recoverable from Git history, using a normal deletion commit without rewriting history. Preserve reproduction source, pins, hashes and safe result summaries. Do not delete untracked unique files, active work or sole evidence. No deletion was performed in this checkpoint.
