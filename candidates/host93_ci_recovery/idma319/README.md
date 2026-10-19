# New CI iDMA 319-source extraction candidate

This is a new SOURCE contract. No approval of the lost earlier candidate or
SELECTED_SOURCE_PLAN is inherited. No CI job was started, no repository file was
changed, no network request was made, and no real iDMA archive was read or
extracted during this preparation.

## Parent integration

Copy the reviewed `extract_idma.py` into the parent's CI candidate. Use the
fixed same-buffer Python bootstrap in `ENTRY.json`, with Python `-I -S -B` set
before any local source loading. Supply the extractor's absolute source path as
the loader argument; the loader removes it before the extractor parses its two
actual arguments: `--archive ABSOLUTE_PATH --out FRESH_ABSOLUTE_PATH`.

The bootstrap checks a fixed source byte length and SHA-256, traverses source
ancestors without following links, checks before/after/current stat identity,
and compiles exactly those checked bytes. There is no source importlib import,
bare exec of local bytes, subprocess, or outer process supervisor. Without both
archive/output arguments, the no-argument entry only emits SOURCE status.

The parent owns the authenticated download from the fixed artifact and must
record the external Python exit code and elapsed time. This worker does not
read tokens or implement downloads. A completion report alone does not prove a
successful process exit or formal acceptance.

## New selection contract and provenance

Read-only checkout HEAD was verified as
`18e757084e4812fe2496ba8321438a468e17b646`. Its published acquisition
`plans/idma.json` fixes archive size 9926876 and SHA-256
`a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce`.
The published successful export `VERIFICATION.json` independently records the
manifest and closure digests, the other metadata digests, tc_clk, Bender.lock,
294 sources, 312 admitted inputs, and 8 include directories. The published
exporter/parser establish the JSON shapes and @ROOT@ filelist semantics.
Exact read-only evidence paths, byte lengths and hashes are in PROVENANCE.json.

The new runtime contract additionally fixes embedded manifest length 104165,
closure length 73326, ZIP entry count 929, total uncompressed metadata bytes
33777372, SAFE_IDENTITY length 32889, selected count 319, selected size 3072200,
and maximum selected member 907909. These lengths/totals are explicit new
contract requirements from the parent's handoff, not newly observed archive
measurements in this environment. Actual execution must verify them.

The complete archive size/SHA is checked before ZIP parsing. All 929 metadata
entries must be safe unique regular files. Embedded SHA256SUMS and
SOURCE_CLOSURE buffers must pass their fixed size/CRC/SHA checks before JSON
parsing. JSON duplicate keys are rejected. The original manifest must contain
927 paths; its paths plus the manifest itself must exactly describe the 928
idma_export members, with SAFE_IDENTITY the only extra ZIP member.

The pinned closure must admit exactly 312 inputs and agree with the pinned
manifest on every hash. The manifest-authenticated idma.f.in must contain
exactly 294 unique ordered sources, 8 include directories, and the four known
initial defines. The other 18 admitted paths must be headers. The extra clock
source and six metadata/filelist/lock files must be distinct from those inputs,
giving exactly 319 selected files. All selected buffers pass exact size, CRC,
and SHA before any source file is written, then are checked again immediately
before write and read back after writing.

The output is a fresh 0700 root, a sources/ subtree with 0700 directories and
0600 files, and one bounded EXTRACTION_REPORT.json with the complete selected
inventory and ordered source/include/define basis. SAFE_IDENTITY is not
extracted. The original 927-entry manifest remains provenance and must not be
misrepresented as proof that all 927 members were extracted. Historical
preprocessor qualification does not transfer to a different tool/profile.

## Limits and failure behavior

One current Python process only: 60-second total and 55-second work deadlines,
CPU 40 seconds, one allowed CPU, address space 512 MiB, per-file 4 MiB, output
tree 8 MiB, report 512 KiB. No native tool or child process exists. The initial
loader monotonic timestamp includes loading time. Archive raw SHA and stat are
checked again after extraction. Existing output is refused, never overwritten
or deleted. Caught failures preserve partial output and attempt a bounded
failure report and archive post-check. A hard kill or exhausted total deadline
can prevent report completion; the parent must inspect the external exit.

## Cold evidence

17 tests passed under both normal and optimized Python, always `-I -S -B`.
Coverage includes malformed/unselected ZIP paths, duplicate names, encrypted
and nonregular metadata, CRC/size/SHA failures, semantic 319 selection, duplicate
JSON keys, filelist/closure disagreement, archive identity before ZIP parsing,
fresh output/modes/symlinks, failure preservation, and mocked resource limits.
The actual pinned inline loader rejects wrong source length and a same-length
wrong SHA before compile, enforces isolation before local reads, and runs the
source-only path. Neither test run accessed the real archive.
