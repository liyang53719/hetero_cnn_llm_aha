# Portable observer/policy excerpt

This is a source-inspection package, not a standalone executable candidate.
Seven files are copied byte-for-byte from the frozen single-arm M2 source:
`cached_wholeblock.py`, `narrow_fullblock_attention.py`, `FRAME_ROUTING.json`,
`POLICY.json`, `CODEC_PINS.json`, `anchors.json` and `README.md`.
No validated code was rewritten to make it portable or runnable.

The exact README describes the original source/cold proposal and its execution
boundary. `SUMMARY.md` and `SUMMARY.json` separately report the subsequently
reviewed single actual M2 result. The underlying `POLICY.json` covers the
`op-evidence-boundary-v1` policy; the added routing contract is in
`FRAME_ROUTING.json`. Neither file is an execution grant.

## Check the excerpt

    python3 candidate_attention_m2_frame_routing_public_20261021T0642/check_portable.py --manifest-sha256 TRUSTED_MANIFEST_SHA256

Replace the placeholder with the separately supplied manifest SHA-256. Omit the
option only when a separate manifest trust anchor is not available. The checker
verifies the exact file inventory, file lengths and hashes, then compiles Python
source in memory without importing or executing it. It performs no tests,
baseline access, native initialization, model execution, decoding or networking.
It writes no bytecode, outputs or execution grants.

The manifest uses relative file names and cannot hash itself. Its source and
review provenance pins refer to omitted private originals, not evidence that
this checker independently revalidated. The summary is a bounded transcription
of the pinned independent review, not a new actual-run receipt.

The remaining source closure, original manifests, machine-specific budgets,
launch/supervision/authority files, runtime dependencies, inputs, model/native
payloads, arrays, event streams, raw logs and review receipts are deliberately
omitted. References to omitted modules or dependencies are not patched out.
Successful compilation does not establish that this excerpt can run by itself.

The earlier SOURCE/SYNTHETIC excerpt is a separate frozen package and was not
modified. This package grants no actual execution, M128, fullblock, numerical,
RTL or publication authority.
