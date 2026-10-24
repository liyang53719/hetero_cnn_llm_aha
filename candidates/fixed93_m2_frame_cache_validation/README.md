# Callback-local frame-code cache: wiring excerpt and limited M2 summary

This is a finite, portable publication excerpt. The 13 Python source files are
exact copies from the frozen 0503 candidate: authority, entry, context, runtime,
I/O guard, supervision gate, coordinator, native adapter, success driver, both
cached observers, and parent-only history comparison/decoder. Their original
relative paths, sizes and SHA-256 hashes are in `PORTABLE_MANIFEST.json`.

This is **not an independently executable runtime**. The source may refer to
its original manifest, external baseline, history pins, admission and supporting
modules; those are intentionally absent. Do not run the copied entry, coordinator,
driver, native adapter or parent decoder from this excerpt. No runtime execution
authority is granted or inherited. No frozen source or run artifact was modified.

## Static verification

From this directory:

```sh
python3 -I -B check.py
```

Optionally verify every copied source against the original frozen source root:

```sh
python3 -I -B check.py --original-source "$ORIGINAL_0503_SOURCE"
```

The checker verifies finite whitelist closure, sizes/hashes, private-path hygiene,
source compilation without execution, safe-summary arithmetic and claim limits.
It does not import target modules, run source tests, load native code, decode
streams, or revalidate actual-run evidence. Compilation produces no bytecode
files. The manifest is a hash inventory, not a signature or independent trust
root. Publish only its `publish_whitelist` files.

## What changed

Only the per-callback `frame.f_code` binding optimization is newly exercised:
`TraceDispatcher._dispatch` and `Fixed93FullblockAttentionObservation._trace`
read it once and reuse the local code object. Parent-frame reads, callback
registration, numeric operations, recorded fields and schemas remain unchanged.
The pre-existing `op-evidence-boundary-v1` policy remains in force; this cache
candidate does not further reduce integrity-check frequency.

The [Python frame documentation](https://docs.python.org/3.12/reference/datamodel.html#frame.f_code)
describes `f_code` as read-only and audited. Audited read counts intentionally
fall on applicable paths. Compatibility is limited to the pinned guards that
ignore that event, not arbitrary stateful/mutating/raising audit hooks or
asynchronous signal timing. The public source is not rewritten to hide generic
OS path constants or the authority-role label; no private machine-specific
absolute paths are included.

## Limited result

`SUMMARY.json` is a deliberately selected summary of reviewed evidence, not a
raw receipt. The reviewed 0503 single new finite N1 synthetic M2 run matched the
sealed historical 0417 new arm within the stated observer-equivalence scope:

- 51 closed output files, 6,019,366 bytes, were reviewed after exit.
- All 33 field/presence/output files and transport matched exact size and SHA.
- Decoded semantics matched across 8,565 Attention and 2,211 wholeblock records.
- Raw logical records were not all byte-identical: 3,391 Attention and 1,515
  wholeblock records differed. The comparison accounted for 11,011 explicitly
  allowlisted opaque-ID difference rows, four long-lived bidirectional mappings,
  and known generic references. It does not prove arbitrary short-lived
  cross-run alias equivalence; no tag or epoch normalization was used.
- Historical main-loop CPU was 32.520110039 s versus 27.504084966 s, a 15.42%
  reduction. Wall time was 33.802740322 s versus 28.343136417 s, a 16.15%
  reduction. These are historical single runs, not repeated concurrent pairs.
  No confidence interval, full-size projection or microbenchmark factor applies.

The result is **M2 observer equivalence only**, not independent numerical
acceptance, M128, RTL or fullblock PASS. Wholeblock remains INCOMPLETE: public
advance calls, jobs, completed count and PC are all zero; no original fullblock
seal was called. No new actual or source test was run to prepare this excerpt.

The earlier 0437 diagnostic remains **FAIL / INCOMPLETE_SAMPLING**. Its 3,134
auxiliary samples are partial hotspot evidence with one detected reentrant drop,
not PASS or complete profiling. No failed or otherwise unsealed stream was read
for this publication. The 0503 run had sampling disabled.

## Provenance and omissions

The manifest and summary pin the original frozen source manifest, source/cold
review, actual review, and failed diagnostic review by size and SHA-256. The
actual review is 31,211 bytes with SHA-256
`39c51ac6aa3eff3e6778417a7f5924117f2883cb71e404c85f3074fef978bcdf`.
These provenance references do not make the omitted private evidence publicly
reproducible; they bind the summary to the reviewed local evidence.

Intentionally omitted: original source manifest, HISTORY, ADMISSION, cold/actual
receipts, profile payloads, event streams, ID-row payloads, input/output arrays,
native ELF, runtime dependencies, and machine paths. A future reproduction
requires separately authorized, fully pinned inputs and runtime, not edits that
bypass the excerpt's missing authority or source gates.
