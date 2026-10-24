# Tick-boundary metadata policy: actual wiring excerpt and limited M2 summary

This finite publication contains 13 exact Python source files from the frozen
0526 candidate plus its exact `TICK_POLICY.json`. The source selection covers
authority, entry, context, runtime, I/O and supervision guards, coordinator,
native adapter, success driver, both observers, and parent-only decoder/history
comparison. Original relative source names, sizes and SHA-256 pins are recorded
in `PORTABLE_MANIFEST.json`. No production source is rewritten or reformatted.
The earlier 0517 source/synthetic public package remains separate and unchanged.

This is **not an independently executable runtime**. Copied helpers reference
original manifest/authority/history/baseline/support files that are deliberately
not included. Do not run the copied coordinator, entry, native adapter, driver or
decoder from this excerpt. The reviewed invocation does not authorize a new one.

## Static checker

From this directory:

```sh
python3 -I -B check.py
```

Optionally verify each source copy against the original frozen 0526 directory:

```sh
python3 -I -B check.py --original-source "$ORIGINAL_0526_SOURCE"
```

The checker verifies finite whitelist closure, file pins, private-path hygiene,
source compilation without execution, summary arithmetic and claim limits. It
does not import targets, rerun original tests, load native code, decode streams,
or independently repeat actual evidence verification. Compilation writes no
bytecode files. Hash inventories are not signatures or an independent trust root.
Publish only the manifest's `publish_whitelist`.

## Reviewed limited actual result

`SUMMARY.json` is a selected safe summary, not an original receipt. The review
confirmed one finite N1 synthetic M=2 Attention run under the new tick-boundary
metadata-integrity policy. Its observer-output comparison used the sealed
historical 0417 new arm, not an independent numerical oracle:

- 51 closed output artifacts, 6,014,897 bytes.
- All 33 field/presence/output files and transport matched exact size/hash.
- Empty decoded semantic differences across 8,565 Attention and 2,211 wholeblock
  records, under the original explicit identity-comparison rules.
- Raw logical records were not all identical: 3,391 Attention and 1,515 wholeblock
  records differed. The comparison accounted for 11,011 allowlisted opaque-ID
  difference rows, four long-lived bidirectional mappings and 1,515 known generic
  references. Short-lived cross-run alias equivalence is not proven; no tag or
  epoch normalization was applied.

This is **historical M2 observer equivalence only**. Wholeblock remains
INCOMPLETE: public advances, jobs, completed count and PC are zero, and no
original fullblock seal was called. It is not M128, RTL, fullblock PASS, official
input/reference validation, or independent numerical acceptance. No unsealed
old stream or historical child-input payload was read in the reviewed run.

## Historical timing, not a throughput guarantee

Compared with the historical 0503 callback-cache run:

- Main-loop CPU: 27.504084966 s to 16.407840106 s, down 40.34399%.
- Main-loop wall: 28.343136417 s to 16.902397798 s, down 40.36511%.
- The new actual invocation's outer wall was 25.824388974 s, a different scope
  from the main-loop timing.

These are single historical runs, not a contemporaneous pair or repeated
benchmark. The main loop includes the real owner, dual observers, codec and
transport, excluding constructor and sealing I/O. There is no confidence
interval, M128/full-size extrapolation or throughput/resource guarantee. The
semantic comparison baseline and timing comparison baseline are deliberately
distinguished above. No actual or source test was rerun to package this summary.

## New, explicitly weaker integrity contract

`tick-boundary-metadata-integrity-v1` changes full-check frequency. Full old
identity checks remain at specified tick/exception/bootstrap/outside boundaries,
with retained cheap live ownership checks inside a proven active tick. The old
full identity implementation is unchanged, but its scheduling is not equivalent
to every-callback metadata attestation.

ABI/profile values changed and restored entirely within one tick before a full
boundary may go undetected. The successful output comparison does **not** restore
the old transient-tamper detection guarantee. Scope closing is supported by
reviewed control flow, source binding and completed observation, not an
independently counted per-boundary ABI-check trace. The original prior
nonconsumer `_op` exemption remains explicit. No recorded field/schema/numeric
operation is removed by this policy.

## Provenance and omissions

The manifest and summary pin the frozen 0526 source manifest, independent source
review and actual review, plus the source-policy and historical-0503 review
references. The actual review is 35,704 bytes with SHA-256
`087197391d897ef27b1cec68f61ad374be3713af719804de2d107a5e4b1cf1db`.
These references bind local provenance but do not make omitted private evidence
publicly reproducible.

Not included: original source manifest, ADMISSION, HISTORY, original cold/actual
receipts, profile or event-stream payloads, ID rows, input/output arrays, native
ELF, runtime dependencies, or private machine-specific absolute paths. Generic
OS paths and the authority-role label remain unmodified in exact source copies.
The original frozen sources, run artifacts and prior public packages were not
changed. Future reproduction requires separately authorized exact inputs and
runtime, not weakening gates to bypass the deliberately omitted authority.
