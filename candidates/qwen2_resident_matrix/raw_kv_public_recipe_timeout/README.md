# Archived public M128 numeric timeout

This checkpoint preserves a failed run, not numerical acceptance. It records
`TIMEOUT`, phase `numeric`, and elapsed time **2587.336054 seconds**. The run
started its numeric stage, but postflight and numerical acceptance remained
false. Full-29-node acceptance, Scala execution, and RTL execution were false.

Original provenance supplied with the artifact:

- Run: `38952336951`; job: `117146548710`; artifact: `12071740663`
- Checkout: `ac3a074cd0e29342447844a7675425af628a39ef`
- ZIP: `public-m128-numeric-timeout.zip` (15,278 bytes)
- ZIP SHA256: `85b9554eaedf9904760d1da4363470903dbd04e32c72016c131c55e9c89d4855`

The ZIP was checked against that SHA256 before extraction. `summary.json`,
`progress.json`, and `source_hashes.json` are its exact original member bytes;
`checkpoint.json` records their sizes, hashes, and bounded interpretation. The
ZIP itself is not copied here. The source manifest has 283 source identities
and 12 generated identities. Its values describe the historical run, not an
assertion that a later checkout or this partial source mirror matches them.
Run/job/artifact IDs are supplied provenance; the digest authenticates byte
identity against the supplied digest, not GitHub origin independently.

## Evidence boundary

Setup completion is only a **source-order inference**: the runner enters the
numeric phase after its setup success checks. No private native setup receipt
was preserved in this artifact. Therefore this archive cannot independently
revalidate setup, native dispatch, intermediate numeric stages, final outputs,
or postflight. CPU eligibility is explicitly eligibility-only and is not a
backend-qualification result. No weights, numerical arrays, or private logs
are included. The three fixed diagnostic frame records are safe source/line
metadata, not numerical data or a private log.

## Cold verification

Run from the repository root, with bytecode writing disabled so that the
archive's exact file allowlist stays clean:

```sh
python3 -B candidates/qwen2_resident_matrix/raw_kv_public_recipe_timeout/validate_evidence.py
python3 -B -m unittest discover -s candidates/qwen2_resident_matrix/raw_kv_public_recipe_timeout -p 'test_*.py' -v
python3 -B -O -m unittest discover -s candidates/qwen2_resident_matrix/raw_kv_public_recipe_timeout -p 'test_*.py' -v
# Package-style execution is supported as well:
python3 -B -m unittest candidates.qwen2_resident_matrix.raw_kv_public_recipe_timeout.test_evidence -v
python3 -B -O -m unittest candidates.qwen2_resident_matrix.raw_kv_public_recipe_timeout.test_evidence -v
```

Optionally pass the original ZIP path with `validate_evidence.py --zip PATH`
to compare each preserved member directly to its ZIP bytes again.

Validation is standard-library-only. It rejects changed member bytes,
unknown/missing fields, type confusion (including booleans as numbers),
duplicate keys, non-finite numbers, oversized inputs, unexpected files,
unsafe source paths, and synthetic PASS/acceptance claims. Known historical
values are fixed, and all enforcement survives `python -O`. Cold success
prints `status: TIMEOUT` with `numerical_acceptance: false`; it does not run
setup, native computation, Public numerical work, Scala, RTL, network, or Git.

The tests also support ordinary package/discovery execution without `-B`.
They validate a temporary snapshot of exactly the seven intended archive
files, so interpreter-created `__pycache__` does not contaminate the fixture.
The archive validator itself deliberately rejects `__pycache__` and every
other extra entry; runtime caches must not be included when publishing this
checkpoint. Use the documented `-B` commands to avoid generating them.
