# Historical single-M16 result and limits

The pinned independent review reports
`PASS_ACTUAL_SINGLE_M16_ATTENTION_SCALE_SEALED_STRUCTURE_ONLY` for one synthetic
M16 Attention subchain. This is a report of that completed run, not a new run or
an executable qualification of this excerpt.

## Measured result

- Outer wall time: 283.48977095999 seconds; return code 0.
- Main loop: 245.663893279 CPU seconds and 252.79395813499286 wall seconds.
- Final owned actual inventory: 50 files, 151,549,377 bytes. This is the historical
  actual inventory, not this small public package's inventory.
- Attention records: 268,713. Matrix-only Wholeblock subchain records: 72,393,
  consisting of 44,355 semantic records plus 28,038 operand definitions.
- All 33 field/presence/output files were structurally checked: 16 field arrays,
  16 presence arrays and one 98,304-byte output. Fields plus presence occupy
  3,305,280 bytes.
- All 29,184 accepted memory transactions were structurally checked against the
  source address sequence: 27,648 reads, 1,536 writes and 1,536 write ACKs. Output
  packet bytes and complete output order were checked. QK/PV/normal step counts
  were 1,536 / 13,056 / 14,592. Last ACK and owner result each had four hold cycles.

The original authorized parent ran both complete record decoders to real EOF.
The independent reviewer did not rerun those decoders: it authenticated their
report through source, authority, terminal and byte identities, and independently
checked terminal frames, all fields/presence/output and the complete source
transport sequence. Packaging did not reread any large stream or actual transport,
rerun the original tests, load native code or execute the model.

## Corrections retained explicitly

The fixture is M=16, 12 query heads, 2 KV heads and width 128, with Q/K/V word
counts 24,576 / 4,096 / 4,096. An erroneous KV-head count of 16 was corrected to
2 before source freeze, with exact shape/index checks. The frozen executed source
already contains the correction; this package does not modify executed code.

Initial cold01 ran on Python 3.13. This was a substantive gap for the intended
3.12 target, not a target-3.12 qualification. Separate cold02 used CPython 3.12.14
for 106 source controls plus the real supervision projection, both exiting 0 with
unchanged source. The original non-target cold evidence was preserved. The new
target seal supplements qualification rather than rewriting the earlier evidence.
The actual launch also used the explicit target interpreter. The README gives
the direct interpreter command to avoid an unqualified `python3` substitution.

## Not established

There is no independent numerical oracle, official input/reference acceptance,
historical pair equivalence, M128/fullblock pass, RTL or hardware-cycle acceptance.
The historical run used a genuine existing native ELF and constructor reset/guard
probes; it was not zero-native. The Wholeblock stream is only a sealed subchain,
not a complete schedule/cache or fullblock seal.

M2 and M16 measurements cannot be linearly extrapolated into an M128 or fullblock
time guarantee. Any new full run requires fresh source/cold/authority and current
resource gates. Sampled aggregate RSS and per-process/address-space checks are
not a continuous memory-peak proof; tmpfs consumes resident memory separately.
The declared routing policy weakens transient nonhook ownership/metadata detection;
no predecessor anti-tamper equivalence is asserted.

`SUMMARY.json` and `MANIFEST.json` carry byte-count/SHA-256 pins for the omitted
source manifest, independent actual review and target/non-target cold provenance.
These pins identify historical originals but are not independently revalidated by
this portable checker. The package is source inspection only, not a runnable
candidate, evidence replacement, execution grant or publication authorization.
