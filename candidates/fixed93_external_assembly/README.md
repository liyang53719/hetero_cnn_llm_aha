# Prepare a small PV-reuse source assembly

This standalone tool creates a new source/metadata assembly using three exact
pinned predecessors. It does not copy weights or reference tensors, execute a
DUT, load native code, or launch fullblock preflight. All six paths are required:

    python -I -S -B prepare_assembly.py --baseline BASE --pv-bundle PV --resolver-bundle RESOLVER --output NEW --input-root INPUT --reference-root REFERENCE

The first three roots must match INPUT_PINS.json and the embedded digests. NEW
must not exist and must not overlap an input. INPUT and REFERENCE are explicit
absolute canonical roots; this tool only stats the two directories. The later
real preflight must verify all 76 exact declared files at those roots.

Source reads are bounded and byte-pinned. The metadata generator runs from a
private temporary snapshot of previously verified source bytes. Only exact 321
source/selected/support objects plus small preparation files are copied. The
new top manifest additionally pins production; production does not pin itself.
The receipt excludes its own digest, which is reported separately on stdout.
There is no hash fixed point or old PASS inherited as current qualification.

The total logical-file cap is 9 MiB, including a receipt capped at 256 KiB.
Temporary snapshot bytes are removed before the final files are written and
have their own recorded peak. This is not an OS disk-allocation or RSS proof.
The active Python guard confines writes to NEW and rejects links, relative
write-open, frozen-file opens and native/process/network operations. It is not
an arbitrary native/OS sandbox. Keep the supplied one-CPU, 30-second, 256-MiB
external process limits when reproducing this preparation step.

One separately authorized root execution naturally exited zero and produced
547 files / 8,806,882 bytes. SUMMARY.json gives the bounded scope and identity.
It opened no frozen input/reference files and hashed no runtime payloads.
Its machine-specific receipt is not distributed here. A prepared source tree
is not a verified model result: native/DUT/fullblock/M128 acceptance is absent.

The generated receipt supplies the exact new manifest and a separate full
preflight command. That command still hashes all 321 source objects, every prep
file, 1,638 runtime files and 46 frozen files, and stats 30 reference payloads
without reading them. It is not a SOURCE_ONLY bypass. The proposed preflight
limit is 120 seconds / one CPU / 256 MiB; it must be separately authorized and its
actual outcome reviewed. This public summary was sealed before that preflight.

This package contains only portable code, relative prerequisite pins and a
small summary. It does not include payloads, machine paths or old run logs.
