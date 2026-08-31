# Security action required: GoCardless sandbox token

GitHub notified the repository owner that commit `ed06f4cff17633cf6b285dcef2d6fe50de17869b` exposed a GoCardless Sandbox Access Token. Current code search does not find the provider name in the active tree, but a token reported in public history must be treated as compromised.

Required owner action:

1. Revoke or rotate the token in the GoCardless sandbox dashboard immediately.
2. Replace the credential in the local secret store or environment; do not commit the replacement.
3. Review GitHub secret-scanning status after revocation.

The project now enforces main-only, fast-forward-only history, so this task does not rewrite public history or force-push. Revocation is the security boundary. A history purge would require a separate explicit user authorization and coordinated clone invalidation.
