# Portable Host93 emission source

This package is SOURCE-only. Static checks and 42 tiny pure cold checks passed. No acquisition, production assembly, Scala compilation, CHIRRTL emission, firtool run, or new RTL generation has run locally. Full-block RTL passes remain zero.

## Entry

Use Python `-I -S -B`. Read `host_emission.py` once, compare its size and SHA-256 with `ENTRY.json`, then compile that same buffer into a module. Call `run(repo, work, call_phase)` only inside the separately authorized CI job. `work` must not exist and must be outside the checkout. The caller supplies the shared 6600-second job deadline and a CPU1 process-group runner.

The callback receives `(name, argv, cwd, environment, limits)` and returns `record`, `raw_log` (bytes), `usage`, and `evidence_root`. Its original record must have exit code zero and confirmed process-group cleanup. It must raise on failure. Limits use `total_seconds`, `work_seconds`, `cpu_seconds`, `as_bytes`, `fsize_bytes`, `log_bytes`, and `sample_rows`. All phases are single-attempt; there is no retry, fallback tool, implicit install, or native execution in static mode.

The runner must already provide Java 21. Selection is `JAVA_HOME_21_X64`, otherwise `JAVA_HOME`; release bytes and a bounded version probe must agree. The actual Java binary and release file are measured before and after use. No historical machine-specific identity is treated as evidence.

## Reconstruction and evidence

121 project-relative SHA-256/size pins cover the 111 replay inputs and the published assembler, acquire utility, fixed official acquisition plans, compiler/emitter/SV command builders, and single-member firtool helper. Sources are read into verified byte buffers and frozen before any recipe is compiled. The published assembler creates 93 new Scala sources from project inputs plus the 20 pinned HardFloat sources. Compiler and emitter arguments come from the published command builders; local historical gate handshakes are not called.

jar87 uses the fixed Maven plan; HardFloat20 uses its fixed upstream revision; firtool is the sole allowlisted member of the official 1.62.1 archive. Acquired files and compiler inputs are measured before/after use. Runtime records retain actual classes, FIR/SV, logs, tool identities, complete bounded tree inventories, and original callback receipts. Expected FIR/SV hashes are acceptance tests, never substituted evidence. A mismatch preserves the measured result in `HOST_EMISSION_FAILED.json` and raises.

Successful output is `HOST_EMISSION_RESULT.json` plus JSON-friendly return data. `paths` contains `source`, `classes`, `jars`, `hardfloat`, `fir`, `sv`, `firtool`, and `frozen_repo`; `identities`, `inventories`, and `phases` contain the actual evidence. Top-level `fir`, `sv`, and `firtool` aliases each contain `path`, measured `bytes` and `sha256`, and actual octal `mode`. This qualifies generation only, not semantic correctness, Host execution, runtime dependency closure, or numerical behavior. Java identity records cover the selected launcher/release, not a claim that every installed JDK or system-library byte was pinned.

## Local source checks

- `python -I -S -B host_emission.py --repo /path/to/checkout` reads fixed project-source identities only.
- `python -I -S -B test_tiny.py` exits before loading the candidate.
- `python -I -S -B test_tiny.py --execute-cold` runs only tiny generated fixture checks, including actual Python bootstrap children in normal and -O modes with marker-based before-compile rejection tests. It performs no network/toolchain/Scala/firtool work.

## v2 guard correction

The v1 package is preserved separately and is not the integration target. v2 replaces all bootstrap assertions with explicit rejection, checks -I/-S/-B before imports or source reads, and uses no-follow descriptor-relative traversal plus same-descriptor and current-name stat identity checks. The actual bootstrap is tested with valid, short, same-size bad-hash, and missing-flag fixtures in normal and -O interpreters. jar87 address space is restored to 512 MiB; assembly CPU to 40 seconds; acquisition work stops leave the existing 15-second cleanup/postflight reserve.


## New narrow CI transport delta
Only fixed acquisition phases inherit the existing proxy/CA variable allowlist verbatim; values are never included in receipts or public evidence. Native phases remain clean. No direct fallback or credential setup exists.
Emission exception records explicitly reset status to INCOMPLETE even if finalization fails after its provisional success status.
