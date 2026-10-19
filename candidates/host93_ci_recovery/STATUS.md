# Host93 CI recovery: TEMP_SOURCE

This directory is work in progress. The fixed iDMA artifact downloader and its ten synthetic tests have passed local normal and optimized Python tests. No current CI job has executed this downloader. No complete Host run, numeric pass, or current local binary is claimed.

The downloader requests only artifact 12099239717 from this project's GitHub Actions API, checks its exact 9,926,876-byte SHA256 identity, and leaves it opaque. Its short-lived job token is sent only to the exact API request. The subsequent signed HTTPS body request carries no application Authorization header. Existing platform proxy settings are retained. Signed URLs, tokens, raw logs, weights, generated binaries and machine inventories must not be committed or uploaded.

On 2026-10-19 at 00:38 UTC, the working environment was observed to have reverted to an older snapshot. The published source and historical safe results through commit 18e757084e4812fe2496ba8321438a468e17b646 remain recoverable. The newer local tool binaries, micro artifacts and unpublished Host recovery candidates are unavailable in that restored workspace. Historical passes do not establish that missing current assets exist.

The next implementation will run fixed source acquisition, the reviewed initialization patch, one tool build, the synthetic micro, and a bounded Host reset/launch in one GitHub job. This source-only checkpoint has no launch workflow. The complete job must pass a separate source review before its once-only workflow is published.

## Temporary-data policy

Small source checkpoints must be pushed promptly and identify PASS scope, TEMP_SOURCE, or FAIL. Check temporary tracked files hourly. Daily cleanup may remove only confirmed unnecessary tracked temporary data recoverable from Git history, using a normal deletion commit without rewriting history. Preserve reproduction source, pins, hashes and safe result summaries. Do not delete untracked unique files, active work or sole evidence. No deletion was performed in this checkpoint.
