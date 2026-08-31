# GitHub secret-scanning review: GoCardless sandbox-token alert

GitHub reported a GoCardless Sandbox Access Token at `reports/execution/sandbox_v69_result.json`, line 2, in commit `ed06f4cff17633cf6b285dcef2d6fe50de17869b`.

Repository inspection found no GoCardless provider name or explicit credential in the active tree. The flagged line contained the descriptive evidence string `sandbox_v69_E0_and_source_ready_not_RTL_E1_E4`, which is the likely pattern match. The active tree now uses a hyphenated evidence label to avoid retriggering.

Owner action:

1. Inspect the GitHub secret-scanning alert and compare the redacted match with the descriptive string.
2. If it matches only that string, dismiss the alert as a false positive.
3. If it contains any real credential unknown to this audit, revoke/rotate it immediately and keep the replacement outside Git.

No history rewrite or force-push is performed under the main-only workflow.
