# Offline eight-artifact verification

This separate standard-library tool verifies public JSON and source identities
for commit `8ba333c76722b47b681be88612b1c6987e34a5f4`, run `39017864296`, job
`117353555753`. It does not execute the model, compile native code, fetch GitHub,
install packages, control processes or read absent private payloads. It is not
part of the running workload or its frozen source inputs.

The validator accepts only the exact eight-member successful artifact inventory.
A failed or partial attempt must first be preserved and diagnosed separately;
this success validator rejects it rather than creating missing receipts. The
full numerical receipt can remain valid when a later metadata step fails.

Before invoking the CLI, the coordinator must independently retrieve and verify
GitHub's terminal run/job metadata and artifact ID/digest. The CLI binds those
operator-supplied values and explicitly reports that it did not fetch them.
A structural PASS on a synthetic fixture is only a test result and cannot
establish that an actual execution occurred. Its test fixture hashes are not
actual tensor measurements.

The complete validator checks its fixed local schema-source pin before execution:

```
python -I -B verify_artifact.py \
  --artifact /path/to/the/exact/downloaded/artifact.zip \
  --artifact-sha256 SHA256_FROM_VERIFIED_GITHUB_METADATA \
  --run-id 39017864296 --job-id 117353555753 --artifact-id ACTUAL_ARTIFACT_ID \
  --freeze /path/to/same_host_m128_replay_identity_20261017_freeze_cded2ae5 \
  --out /fresh/path/VERIFIED_PUBLIC_REPLAY_IDENTITY.json
```

Output creation is exclusive. Do not overwrite a previous failure or report.
The original ZIP is read into memory, never extracted to filesystem paths.
The eight JSON files are bounded individually and in total; duplicate members,
nonregular members, duplicate JSON keys, nonfinite numbers and noncanonical
receipt serialization are rejected. The source map and all465 frozen source
files are rehashed, then both actual-commit source contracts and child-result
receipts are reconstructed without numerical imports.

`identity_schema.py` checks the public tensor inventories and cross-references.
Its source hash is pinned and checked before the CLI can issue a complete result. Private
file hashes, qualification hashes and process-proof hashes remain commitments:
reading a public record does not replay its absent private body. A later RTL
regeneration can compare new bytes to the retained canonical content hashes;
this verifier itself does not regenerate the values or grant RTL acceptance.

The identity artifact alone cannot confer readiness. The exact whole-file hash
must match the successful parent receipt with replay_identity_ready=true; the
stable identity hash is separately checked against its canonical identity body.
The source-declared parent deadline/postflight requirements remain in force.

Cold tests:

```
python -I -B test_verify_artifact.py
python -I -B -O test_verify_artifact.py
python -I -B test_identity_schema.py
python -I -B -O test_identity_schema.py
python -I -B test_cli.py
python -I -B -O test_cli.py
```

The receipt-only fixture deliberately starts with an incomplete identity body
for local receipt-function tests. It cannot pass the complete identity/CLI
validator. A complete synthetic schema fixture is used separately for integrated
success/rejection tests, with its synthetic nature recorded explicitly.

## Generated compile-source correction

The original offline kit rejected the authentic successful artifact with
SCHEMA_VALUE at provenance.combined_library.source_map_sha256. It expected the
four raw checkout hashes, although the tiny compiler actually reads its generated
profile2 source tree. Only matrix_numeric.cpp differs: raw SHA7702e597... versus
authenticated generated SHA1ddf017f.... The unchanged source-bound compile receipt
therefore reports map0e298008..., rather than the raw-map802d3495....

This separate successor reads the exact hash-pinned tiny input contract, verifies
all114 input pins and the exact two generated targets, then applies the generated
overrides to its four declared arithmetic files. The resulting map must also
match both independently authenticated M16 and M128 composed-source contracts.
The schema receives that map explicitly. No value is copied from the artifact
to make the expectation pass. Other public schema and receipt checks remain in
force; a manifest with the old raw-map hash is rejected.

The original kit, first rejection, source diagnosis and authentic ZIP are
preserved. This is a correction to offline verification only. The numerical
workflow, emitter, artifact and runtime are unchanged; no numerical rerun occurs.
