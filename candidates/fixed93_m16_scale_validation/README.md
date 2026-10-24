# M16 Attention scale: portable source excerpt

This small source-inspection package contains exactly three byte-for-byte files
from the frozen M16 source: `success_driver.py`, `parent/seal_check.py`, and
`tests.py`. `SOURCE_PINS.json` uses relative file names and preserves their
original byte counts and SHA-256 values. No validated source was rewritten for
portability. The new README, summaries, manifest and checker describe the excerpt,
not a replacement source or an execution grant.

## Contents and boundary

- `success_driver.py`: synthetic M16 fixture, bounded real-owner loop and finite
  subchain seal helper. Its required owner, runtime and observation objects are absent.
- `parent/seal_check.py`: parent-only structural validator. Its original decoder
  dependencies and all actual evidence are absent.
- `tests.py`: original source-control test text, retained for inspection only.
  Its authority/runtime/source dependencies are absent. Do not run it from this package.
- `SUMMARY.md` and `SUMMARY.json`: bounded transcription of pinned historical
  reviews, not newly generated actual evidence or an independent numerical result.

This is NOT a complete runnable candidate, dependency closure, authorization
bundle, or evidence archive. References to omitted modules are deliberately not
patched out. Compilation does not establish standalone executability.

Original manifests, budgets, machine-specific paths, execution grants, read
routes, payloads, input/reference/output arrays, streams, actual transport,
raw logs, runtime/native dependencies and original review/cold receipts are
omitted. Historical provenance is represented only by byte counts and hashes.
A provenance pin does not mean the portable checker revalidates omitted evidence.
The only absolute path below is the explicit target interpreter command, not a
private input, output, evidence, dependency or authority location.

## Safe static verification

From the directory containing this package, use the target CPython 3.12 interpreter
explicitly, not an unqualified `python3` that may resolve to 3.13:

    /opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python -I -S -B candidate_attention_m16_scale_public_20261021T0717/check_portable.py --manifest-sha256 TRUSTED_MANIFEST_SHA256

Replace the placeholder with the separately supplied manifest SHA-256. Omitting
it verifies internal consistency only, not an external trust anchor. On another
machine, select that machine's CPython 3.12 explicitly; do not interpret a local
checker pass as replay of the historical target cold or actual run.

The checker checks exact inventory, relative paths, regular non-symlink files,
byte counts and SHA-256, then parses and compiles Python source in memory. It does
not import or run any candidate file, run the original tests, initialize native
code, load a model, decode streams, read omitted evidence, write bytecode or grant
authority. Do not run the copied driver, parent validator or original test script.

This excerpt grants no new actual run, M128, fullblock, numerical, RTL, hardware,
or publication permission. Earlier M2 source/results and authority are separate
and are not inherited.
