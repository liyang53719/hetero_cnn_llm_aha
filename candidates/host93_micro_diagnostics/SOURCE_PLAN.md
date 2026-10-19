# Fixed implementation and execution contract

Parent baseline: cf01cf5f718ac150ef21b34beaf61195e09fa299. Existing Host and build-only code/workflows remain unchanged. A new entry is projected to candidates/host93_micro_diagnostics/run.py. Parent owns the independent workflow and all native execution/publication.

Interface:
- Actual: python3 -I -S -B candidates/host93_micro_diagnostics/run.py --execute --repo REPO --out OUT --deadline HOST93_WORK_DEADLINE.
- Safe validation: the same entry with --verify-evidence --out OUT.
- Without explicit execute arguments it refuses native work. The workflow binds the reviewed git SHA and first attempt. Project imports use size/SHA-verified same buffers; the entry's own bytes are observed and rechecked, while the workflow git SHA binds its launch.

The workflow establishes t0 before checkout: full job deadline t0+6600, work deadline t0+6480, leaving 120 seconds for safe validation/upload. The entry uses that same work deadline and never restarts a 6600-second window.

Fixed sequence:
1. Icarus acquisition/staging: 120 seconds total, 90 work, 40 CPU, 512 MiB AS, 4 MiB FSIZE, 16 MiB private selected tree, 64 KiB merged log.
2. FIFO compile and FIFO vvp: each 30 total / 10 work / 10 CPU, 512 MiB AS, 4 MiB FSIZE, 8 MiB tree, 64 KiB merged log.
3. The unchanged original 20 fixed Verilator source, host-tool probe, FlexLexer header, build and tool-tiny stages. Existing per-stage limits remain; make stays 3600 total / 3570 work / 4 GiB AS. The shared wall can stop the sequence sooner.
4. Transparent then opaque generation: each the same 30/10 micro limits. Opaque is last. Its real nonzero terminal record remains FAILED; a narrowly recognized expected model observation may produce DIAGNOSTIC_OBSERVED overall. No Host qualification is granted.

Official Icarus package: https://archive.ubuntu.com/ubuntu/pool/universe/i/iverilog/iverilog_12.0-2build2_amd64.deb, 2125764 bytes, SHA256 f19394cee05ad526e0eb3873bc6c17a5828f56df17fbe2db40cb66513a2d4667. Exact whole-buffer identity precedes archive parsing. The package is Zstandard. A bounded existing host libzstd capability is privately identified via a protected same-inode file descriptor before network access. Each single frame must decode to the exact fixed tar size/SHA, followed by the literal 39-member size/SHA allowlist. No package installation, generic extraction, or library download occurs.

Selected package files total 6379063 bytes; the largest is 2873976 bytes. The 21 selected ELF files have a fixed seven-soname direct dependency union. Fixed current host library candidates and their ELF metadata are privately read and rechecked; this is not a capture of every loader-mapped library. The actual compile/vvp phase supplies linkage/function evidence. Generated vvp module references must stay under the staged ivl directory. Explicit staged-vvp invocation avoids the generated system-path shebang.

FIFO qualification requires four exact CASE lines (1294,1294,1296,1296), the exact PASS line, then the fixed fixture-line-229 Icarus finish notice with bounded picoseconds. The standard sixth notice is supported by the v12 upstream finish implementation; it is not dropped as unknown text.

The retained official Verilator commit is 4e194cc3ec8e27b18e17f80d7f99c15f984bbdae, with the existing sole m_seqnum initialization source delta. A missing prior backend supplies no current executable qualification. The paired model must use the newly qualified backend in the same job.

Evidence under OUT/evidence is exactly summary.json, source_hashes.json, and stage_exits.json. Strict schema binds statuses to the stage prefix and actual terminal observations. Every failed stage attempts the existing bounded redacted tail collection. No perfect generic secrecy claim is made; this is the finite public-source, no-weights job scope.

V2 inherits the frozen v1 source and its limited review except for the three strict consumer associations above. The portable cold entry is a separate reviewed test-only replacement. Neither changes execution or expands qualification.

Independent SOURCE acceptance: review_host_micro_job_source_v2_20261019T0621, MANIFEST SHA256 f1b32efd6d010ab67984d86730dbd339532e4e889b7a9170c4f5f9bd569edd01; SUMMARY SHA256 c7e8cb9221b88a2114201173b56822a33f2c92138cf837f8baef42ad15f60bb6. Verdict: SOURCE_GO_FINITE_25_STAGE_FIFO_AND_MODELED_HOST_MICRO_JOB. Actual remains NOT_EXECUTED.
