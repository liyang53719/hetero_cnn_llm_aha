# M2 calibration observation summary

Status: CONFIRMED_MATCHED_SUCCESS_M2_OBSERVER_EQUIVALENCE_ONLY.
The independent final actual receipt was sealed at 2026-10-21 04:35:34 UTC.
Its SHA-256 is 8055216d02e43c73d62a6fefaea64f32498965421631c5028e53f9b758f5a9c4
(40,115 bytes). Its bytes/hash and narrow conclusion were checked during
packaging. This summary is source-bound and limited to that review, not a new
execution receipt. Original private run evidence and the path-bearing receipt
are intentionally not distributed; this bundle alone cannot reverify the run.

## Failure history retained, not overwritten

- 0337 actual attempt failed before ELF loading because the permitted read
  projection omitted the required Git-mirror source read.
- 0407 actual attempt failed after ELF load/configuration, before owner/reset,
  because canonical fixed93 imports were missing.
- 0417 source fixes address those two startup issues while preserving both
  original failures as failures. Packaging did not alter any candidate or run.

## Reported 0417 pair, with narrow meaning

Only the 0417 actual pair is reported as completing: both fresh old/new arms
exited naturally with status 0; reported shared pair elapsed time was 85.059 s.
The review rehashed 97 owned files totaling 10,958,996 bytes and matched four
sealed stream hashes. All 33 raw value/presence/output files (16 field arrays,
16 presence files, and output) and transport JSON were independently checked
byte-for-byte equal. The actual decoded semantic diff was empty, with 11,011
opaque-ID difference rows closed against the explicit allowlist and binding
rules. The reviewer reconciled the pinned decoder control and sealed artifacts;
it did not re-execute the DUT or decoder.
This is differential observation equivalence, not independent numerical proof.

The exact opaque fields in `source/decode_diff.py` are `job_object`,
`owner_object`, `matrix_object`, `scalar_object`, `fifo_object`, `request_object`,
`result_object`, `done_object`, `actual_object_reference`, `adapter_reference`,
and `output_reference`. Their raw cross-process values are not required equal;
differences are retained in the private run evidence rather than erased.
Long-lived job/owner/matrix/scalar identities require bijective correspondence.
Short-lived identity alias equivalence across runs is not proved; None-versus-
object remains a semantic mismatch. Epochs and tags are not normalized.

Reported main_loop CPU time: old 34.917529478 s; new 32.520110039 s.
The difference is 2.397419439 s, a 6.865948% reduction (about 6.866%).
This is not an 18.33x overall speedup, not an end-to-end performance guarantee,
not an M128 result, and not numerical-correctness qualification.

Wholeblock remains INCOMPLETE_WHOLEBLOCK. Finishing the finite M2 observation
stream is not a fullblock seal. There was no fullblock seal, public advance or
reference-payload validation; no full48-domain, M128 or RTL acceptance follows.
Native initialization did occur in the reported actual run and is not described
as zero-native work.

## Packaging validation

The package contains only source, explanatory metadata, and an inert checker.
Packaging validation is limited to exact copy/hash checks, static path review,
in-memory compile checks, and small stdlib checker self-tests. No actual,
native/model, original preflight, original test-suite or expensive test execution
was performed for this package. The final independent receipt establishes only the narrow M2 observer-
equivalence conclusion above, not general correctness or fullblock acceptance.
It also records that equivalence does not mean identical transient anti-tamper
cadence, and cumulative/leader RSS observations are not an exact simultaneous
process-tree peak. A single pair establishes neither long-run duration nor
6,600-second feasibility. Earlier cold01/cold02 failures also remain preserved.
