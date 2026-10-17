# Portable offline public replay-identity verifier

This source-only package reconstructs the exact **465-file content closure** used
by the unchanged offline verifier for source commit
`8ba333c76722b47b681be88612b1c6987e34a5f4`. It needs a local checkout and Python's
standard library on POSIX (Linux/macOS with directory-fd and `O_NOFOLLOW`
support). It does not need the original cloud workspace or any pre-existing
freeze directory. It does not run Git, fetch the network, install packages,
compile native code, execute model/runtime entry points, or regenerate tensors.

The package includes `PACKAGE_HASHES.json`, a SHA-256 inventory of every other
package file (the inventory excludes itself). Check it against the trusted
publication before use. The seven original Python files are byte-for-byte preserved. Their hashes and
the preserved original README/checklist are in `pins.json`. The original
`verify_artifact.py` hash is
`21a29376b04bfa0e83dc05108dbd00b5122188f6dbaeea18a01f6e770c90a5b3`; the schema hash is
`a3585e722c17cc9f7d61b9bb4ac22b74690a2b471308de4851c8a003871c2c11`.
`ORIGINAL_README.md` preserves the earlier instructions for provenance; use the
portable commands below instead of its environment-specific example paths.

## 1. Get the tools and the fixed source separately

These tools were published after the numerical source commit. They are absent
from `8ba333c...`. Keep the trusted tool-package checkout separate from the
following fixed source checkout. `TOOLS` below must point to this directory in
the tool-package checkout; do not check that checkout back to `8ba333c...`.

```sh
TOOLS=/absolute/path/to/trusted-tool-checkout/tools/offline_replay_verifier

git clone --no-checkout https://github.com/liyang53719/hetero_cnn_llm_aha.git pinned-source-8ba333c
git -C pinned-source-8ba333c checkout --detach 8ba333c76722b47b681be88612b1c6987e34a5f4
git -C pinned-source-8ba333c rev-parse HEAD

python3 -I -B "$TOOLS/build_source_view.py" \
  --checkout "$PWD/pinned-source-8ba333c" \
  --out "$PWD/reconstructed-source-view"
```

Use a new output path outside the source checkout. Its parent must already
exist. The builder reads the published
`candidates/qwen2_resident_matrix/portable_same_host_m128_launch/input-contract.json`,
requires its exact SHA-256
`2ac3f216a7e5566fc7dad84c4050502c8afd99d82d9d33e05625bc6f774f1e6c`,
and derives the map from its 464 inputs plus the contract's own hash. The exact
canonical map must hash to
`cded2ae582a6387cddce8c8bbc38c2e1df46a4038c1d3460bf7566f3273e5228`.

The builder copies those 465 files, exactly 6,689,096 bytes, into a private
fresh `source/` directory, with independent single-link files. It rejects
traversal, symlink ancestors, file symlinks/hardlinks, special files, oversized
files, missing files, hash changes and source replacement/drift. It validates
before copying and rechecks afterward. No source file is imported or executed.
Unlisted checkout files, including stale bytecode, are never copied or loaded.
The final `FULL_SOURCE_HASHES.json` is written exclusively after successful
checks. Existing output paths are never overwritten. If interrupted after
creation, leave the incomplete directory alone and retry at a new path.

This is a fixed-content proof for the required closure. The builder does not
claim to authenticate local Git HEAD, the full repository tree, Git history,
or GitHub metadata. It accepts a content-identical export as well as the fixed
checkout. The operator's Git commands above establish the checkout choice;
trust in the published package and its fixed pins is a separate prerequisite.

## 2A. Verify the authentic original ZIP when available

Independently authenticate the GitHub run/job terminal state and artifact
metadata before using this route. The program does not fetch or independently
confirm that metadata. The fixed historical identities are run `39017864296`,
job `117353555753`, artifact `12095858179`, source commit `8ba333c...`, source
tree `bd2c110bb63e39a7a3213e6dea5ffb04dc74ab91` and original ZIP SHA-256 below.

```sh
python3 -I -B "$TOOLS/verify_artifact.py" \
  --artifact /absolute/path/to/original-downloaded-artifact.zip \
  --artifact-sha256 0c25aa1453f5b9f099fdc470933e3074462bd2f92ca08c191a1cfb9adf22b21a \
  --run-id 39017864296 --job-id 117353555753 --artifact-id 12095858179 \
  --freeze "$PWD/reconstructed-source-view" \
  --out "$PWD/VERIFIED_ORIGINAL_ZIP.json"
```

This is the unchanged CLI, including its exact eight-JSON-member ZIP contract.
It reads and hashes the original ZIP container. It rejects partial/failed
attempts, missing receipts, stale schema bytes and inconsistent public bindings.
Never substitute a repacked archive: the same JSON bodies do not reproduce the
historical ZIP's container bytes or hash.

## 2B. Verify fixed published archived bodies

This separate route handles the ten-file published archive: the eight exact
JSON bodies plus `MANIFEST.json` and `README.md`. Its exact member map is
`ARCHIVED_MEMBER_HASHES.json`, SHA-256
`c8c8938bdecae81df68bf08509d9fd729c5e24c4f54ab63e28922e06e335abd8`.
It accepts no caller-selected hashes, artifact IDs or publication identity.

The fixed archive publication is Git commit
`ca5ca9a99eb6c275fd6ab1984bd243c3ca829957`, tree
`fec43509c87d40d645fa9d71467393d4d369a1ce`. These immutable objects and the exact
published content closure were authenticated independently before pinning.
The proof record's SHA-256 is
`23bdb0025fc4b25b904e395c99f4030820d4a8daa7a00b9ab1f6c482cd37b265`.
This identifies a fixed publication object, not an assertion about today's
branch head. `archive_publication.json` is hash-pinned in the adapter; absent,
pending or altered pins fail closed.

```sh
git clone --no-checkout https://github.com/liyang53719/hetero_cnn_llm_aha.git archived-evidence
git -C archived-evidence fetch origin ca5ca9a99eb6c275fd6ab1984bd243c3ca829957
git -C archived-evidence checkout --detach ca5ca9a99eb6c275fd6ab1984bd243c3ca829957
```

Then run:

```sh
python3 -I -B "$TOOLS/verify_archived_members.py" \
  --archive-checkout "$PWD/archived-evidence" \
  --freeze "$PWD/reconstructed-source-view" \
  --out "$PWD/VERIFIED_ARCHIVED_MEMBERS.json"
```

The adapter hashes all ten exact files, checks the fixed publication/member
pins, then uses the unchanged verifier's source reconstruction, receipt checks,
identity-schema validation and provenance checks. Manifest readiness claims do
not bypass any check. Inputs are read-only; output creation is exclusive. The
result is explicitly `ARCHIVED_MEMBER_BINDING`, distinct from the original-ZIP
route. Publication content matches a separately authenticated fixed commit/tree;
the adapter does not replay Git history or check the local checkout's HEAD.

The original ZIP digest is retained only as historical metadata in this route:
`original_zip_bytes_read=false`, `original_zip_digest_recomputed=false` and
`zip_container_recovered=false`. The published bodies can remain verifiable
after the Actions artifact expires, without pretending to recover that ZIP.

## Boundaries common to both routes

- Public identities and receipt consistency do not replay absent private weights,
  input/reference/actual arrays, private qualifications or raw cleanup proofs.
  Their hashes remain commitments to bodies this package does not possess.
- Historical success is limited to 27 assigned official gates per run and the
  observed causal-attention domain. Full-29, RTL and hardware acceptance remain
  false. The explicit mask tensor is missing; scores, logits, probabilities and
  the diagnostic FP32 softmax have limited observation coverage.
- Thirteen loaded-provider records per run are qualified metadata only; the `x`
  provider has a direct-file-rehash claim. Reading public metadata does not
  upgrade those evidence classes.
- Offline verification performs no numerical rerun or regeneration, grants no
  future-job admission, and makes no new performance/latency claim.
- Synthetic test success is rejection/consistency coverage, not proof that a
  numerical execution happened. Actual archived-member checks are identified
  separately in the validation record.

## Reproduce the source-only tests

```sh
python3 -I -B "$TOOLS/test_source_view.py" --checkout "$PWD/pinned-source-8ba333c"
python3 -I -B -O "$TOOLS/test_source_view.py" --checkout "$PWD/pinned-source-8ba333c"
python3 -I -B "$TOOLS/run_original_tests.py" --freeze "$PWD/reconstructed-source-view"
python3 -I -B -O "$TOOLS/run_original_tests.py" --freeze "$PWD/reconstructed-source-view"
```

The adapter suite has 30 tests. The original suite has 102 unchanged tests. The
runner checks all preserved source hashes, copies the seven scripts into a
private temporary package and builds a fresh sibling compatibility source view.
That temporary view's historical directory name only preserves the original
tests' relative-path convention; it is created from the caller's local view,
not read from a cloud freeze. No original script or test method is edited.
Original tests exercise hash-pinned standard-library schema helpers and isolated
verifier CLIs; no model, native build or runtime entry point is executed.

Run the separate 24-case archived-member
adapter suite in both interpreter modes:

```sh
python3 -I -B "$TOOLS/test_archived_members.py" \
  --archive-checkout "$PWD/archived-evidence" \
  --freeze "$PWD/reconstructed-source-view"
python3 -I -B -O "$TOOLS/test_archived_members.py" \
  --archive-checkout "$PWD/archived-evidence" \
  --freeze "$PWD/reconstructed-source-view"
```

All test mutations use private fixture copies. The supplied checkouts and
source view remain unchanged. Tests use only the Python standard library.
