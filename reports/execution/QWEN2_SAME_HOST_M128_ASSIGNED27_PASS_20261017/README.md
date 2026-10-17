# Verified fresh same-host M16 to M128 assigned-27 milestone

Status: PASS_FRESH_SAME_HOST_M128_ASSIGNED27. Commit 2e591b6df29fc08504dca264264b149c27e2cf95, run 39012470402, attempt 1.
GitHub job 117337723540 completed successfully at 2026-10-17T07:44:30Z.

- Run: https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/39012470402
- Job: https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/39012470402/job/117337723540
- Original artifact ID: 12093963949
- Original ZIP SHA-256: f106bdb2820da5f850a17288496613b6bea3b96b414576d36e03a681b529eb62; 46,803 bytes

## Result and scope

The current-job full M16 prerequisite passed before the fresh M128 producer and
independent original-array verifier, followed by full same-host M128. Both full
receipts report 27 assigned official gates, 28 observed official stages, 17 owner
jobs, 21 public completions, 10 capture fields, and one diagnostic FP32 stage.
M16 has 16 rows; M128 has 128 rows. The common attempt nonce is aeab79f18ad512876a9ba55235528adb44e4d99166122f61669ed2d07cd072d3.
M16 child PID 2437 and M128 child PID 2872 report exit 0 and cleanup complete.
The six archived M128 phase records report PASS and observed/final exit 0.
The M16 phase journal itself was not uploaded; only its digest is retained.

Total elapsed: 2191.158994806 seconds. The same-job M16 attempt took
554.653087251 seconds, including full M16 484.61055695 seconds. Full M128 took
1570.271008164 seconds. Timing diagnostics are aggregate parent RUSAGE_CHILDREN
deltas, not operation-level attribution, causal speedup, or future-run guarantees.

This is fresh assigned-27 acceptance. Full-29 acceptance, RTL execution, hardware
recipe acceptance and inherited historical PASS remain false. The terminal
validators explicitly do not authenticate execution on their own.

## What is preserved and independently checkable offline

This directory contains exactly the seven original JSON files, unchanged byte
for byte, plus MANIFEST.json and this README. The manifest pins every original
receipt and the original ZIP, CI identity, source-chain hashes, result scope and
all exposed opaque private references. No raw arrays, weights, native binary,
private qualification, full numerical summary, snapshot or logs are included.

The accompanying standard-library build_verify.py verifies exact original ZIP
membership, hashes and extracted bytes; strict JSON; CI/nonce/exit/cleanup claim
consistency; stage records; and all 463 frozen raw source bytes. The actual
source receipt has 462 raw inputs and 423 static composed M128 files. Its pinned
input contract adds the 463rd raw file. Reconstructing the actual-commit dynamic
M128 SOURCE_CONTRACT produces 424 full runtime sources and manifest digest
273444655b37028e1c417d64fc11b569e043bbff7b41d6bdcc835f81b9288dbe.
The same-job pinned M16 chain has 390 raw inputs, 360 static composed files and
361 runtime sources, with manifest digest
5e2bf0341bb4fa88e1375791e6c5ec3c77df83f7579ed4497f9796dde29fea1c.
Both source-defined CHILD_RESULT objects are reconstructible from public
metadata, and their digests match the full receipts. This checks their exact
expected serialization; the private originals were not independently retrieved.
The composed maps are pinned declarations in the reviewed raw contracts; this
archive check does not execute composition or rederive all transformed files.

## Private runtime validation and replay-identity limit

The reviewed runtime source enforces current-job M16 qualification, same-host and
same-ELF bindings, fresh producer/independent array verification, and full-stage
numerical gates before PASS. Those checks consumed private artifacts on the CI
runner. This archive verifies the public report and source binding; it cannot
independently replay or revalidate the absent private content. Matching opaque
hash references are not the underlying bytes or a cryptographic CI signature.
The M16 and M128 producer_receipt_sha256 fields identify private qualifications,
not the public producer_summary.json.

Retained identities include actual commit/CI/nonce, exact public receipt bytes,
raw and composed source hashes, reconstructed source-contract and child-result
hashes, and opaque hashes for private producer manifest, qualifications, M16
prerequisite, independent verifier receipt, numerical summaries and snapshots.

Source-recoverable expected inputs are retained through the exact public source
pins: model revision ba1cf1846d7df0a0591d6c00649f57e798519da8, thirteen BF16
parameter tensor hashes/shapes, deterministic token/position recipe, fixed input
hashes, read-only arena hashes and table hash. They can check future regeneration
of expected input bytes. The model payload pins are in
config/payload_pins/qwen2_layer0.json; producer driver.py files define the M16 and
M128 input/arena checks. MANIFEST.json also carries the parsed expected input,
parameter and reference-source identities, labeled EXPECTED FROM PUBLIC SOURCE.
Input selection uses deterministic embedding rows, not
the provenance attempt nonce as a random seed.

What is absent is the observed current-run per-stage native/scalar reference,
actual output and capture-field hash inventory, with decoded dtype, shape,
layout and stage-to-tensor correspondence. The native library/ELF and installed
runtime identities are also only indirectly bound by absent private objects.
The opaque private manifest/snapshot hashes do not reveal those values. This
archive is not a replay-ready freeze of historical outputs; expected-input
regeneration and independent replay of this run's observed reference/output
bytes are different claims. The latter needs separately retained per-stage
hash/shape/dtype/layout metadata plus matching bytes or reproducible regeneration
whose identity can be checked. No extra numerical run was performed here.

## Strict cleanup evidence

This run uses the reviewed strict helper
portable_owned_cleanup/strict_cleanup.py, SHA-256
30458e67e84c362ff74d69a702624e91bc3c3089600dd36a2469d9ffd6ec4047,
and strict callers owned_commands.py (c89ea10cf44f92a54c4386907d7c51d3f01e22af750a2d2b1d50df93418f0a4a)
and launch.py (d7ac40bba0fc21b03b19dcdcd886cfffe04d94c04bf8a8d37efc77067c1d5b42).
These replace the historical weak cleanup route for the exercised producer and
phase supervision. The program reports strict proof-validated cleanup complete.
The per-process raw strict cleanup proofs are not uploaded in the seven-file
artifact, so this archive does not independently revalidate process identities,
complete scans, descendant termination, or proof timing. It does not promote the
historical helper flags into stronger evidence or claim a fresh cleanup test.

## Reproduce the safe archive check

From the accompanying evidence workspace:

    python3 -I -B build_verify.py --verify
    python3 -I -B test_build_verify.py
    python3 -I -B -O test_build_verify.py

Optional --actual and --source-freeze locate unchanged original receipts and
pinned raw sources. --build is permitted only in the named unfrozen evidence
workspace. The commands execute no repository module, native/model program,
package installer, process-control fixture, Git command, network request or CI
job. This milestone grants no admission authority for another job, no RTL or
hardware acceptance, and no same-stimulus replay guarantee.
