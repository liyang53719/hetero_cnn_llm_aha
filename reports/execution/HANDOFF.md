# L11 execution handoff

- Canonical stages are L0-L11 from `reports/ARCHITECTURE_AND_EXECUTION_PLAN.md`.
- Current phase: L1 upstream reproduction.
- Every compile, simulation, synthesis, and Docker command uses `taskset -c 8-25`; Docker additionally uses `--cpuset-cpus=8-23`.
- L0 PASS: 27 Python tests, C++ reference, RTL contract simulation, and five 1.0 ns CLN22UL contract DC tops passed. The integrated contract top has WNS 9.75132e-05 ns and zero unmapped cells.
- Docker proxy is now functioning for `hello-world`, and the pinned StanfordAHA image was pulled at `sha256:a8784f2cfe96609a7e4403c29f6a82bd00c882c8564ef747541f78be75fa2b2b`.
- AHA 4x16 image source equals the clean host source at `3b171e813bc5e399b22921c8df20fd4e889f1569`. Gaussian generation, map, PnR and its VCS test all pass; VCS reports a 14.7275 us run and an integer bit-accurate comparison.
- Strict AHA Verilator closure remains open pending its current result. Host Verilator 5.050 rejects upstream `garnet_test.sv` at the `program` interface port. A source-locked, ABI-compatible Verilator 5.028 was instead built locally inside the pinned AHA image; use only `work/toolchain/verilator-5.028-aha` with `AHA_VERILATOR_CXX=g++-10`. See `AHA_VERILATOR_5028_TOOLCHAIN.md`.
- `scripts/write_used_upstream_lock.py` PASSed. It locks the actual Gemmini and AHA Gaussian/PnR dependency closure and intentionally excludes unrelated Chipyard/ Voyager LFS subtrees.
- Fresh Gemmini evidence: Spike mvin/mvout PASS, Spike OS-matmul PASS, Verilator mvin/mvout PASS (669 us), and Verilator OS-matmul PASS (10 ms, 577.7 s wall).
- Spike ResNet50 also passes in explicit `os` mode: 3,053,813 cycles and final `PASS`. The previous `tohost=1337` was a default WS-mode run, not an architectural functional mismatch.
- Gemmini OS Verilator evidence remains PASS. Canonical full WS has a fresh 10M-cycle timeout and its historical 20M `$finish` log has insufficient provenance; see `L1_GEMMINI_WS_AUDIT.md`.
- `lc_shell` was not found; it is only a future L10 SRAM-library dependency.
- Do not close any stage using the existing clean-room-only evidence.
