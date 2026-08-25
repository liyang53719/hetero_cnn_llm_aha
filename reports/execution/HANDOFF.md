# L11 execution handoff

- Canonical stages are L0-L11 from `reports/ARCHITECTURE_AND_EXECUTION_PLAN.md`.
- Current phase: L2 wrapper-only macro integration.
- Every compile, simulation, synthesis, and Docker command uses `taskset -c 8-25`; Docker additionally uses `--cpuset-cpus=8-23`.
- L0 PASS: 27 Python tests, C++ reference, RTL contract simulation, and five 1.0 ns CLN22UL contract DC tops passed. The integrated contract top has WNS 9.75132e-05 ns and zero unmapped cells.
- Docker proxy is now functioning for `hello-world`, and the pinned StanfordAHA image was pulled at `sha256:a8784f2cfe96609a7e4403c29f6a82bd00c882c8564ef747541f78be75fa2b2b`.
- AHA 4x16 image source equals the clean host source at `3b171e813bc5e399b22921c8df20fd4e889f1569`. Gaussian generation, map, PnR and its VCS test all pass; VCS reports a 14.7275 us run and an integer bit-accurate comparison.
- Strict AHA Verilator closure PASS: source-locked 5.028, GCC10/C++20 coroutine support, 4x16 Gaussian generation/map/PnR/bitstream, Vtop, and integer bit-accurate output comparison all pass. Evidence is `work/results/l1_aha_verilator_5028_cxx10_makeflags/` and `aha_verilator_result_audit.json`.
- `scripts/write_used_upstream_lock.py` PASSed. It locks the actual Gemmini and AHA Gaussian/PnR dependency closure and intentionally excludes unrelated Chipyard/ Voyager LFS subtrees.
- Fresh Gemmini evidence: Spike mvin/mvout PASS, Spike OS-matmul PASS, Verilator mvin/mvout PASS (669 us), and Verilator OS-matmul PASS (10 ms, 577.7 s wall).
- Spike ResNet50 also passes in explicit `os` mode: 3,053,813 cycles and final `PASS`. The previous `tohost=1337` was a default WS-mode run, not an architectural functional mismatch.
- L1 upstream reproduction PASS. Canonical full WS uses native `LOADMEM=1` and finishes at 10 ms within the one allowed 20M cap; see `L1_UPSTREAM_CLOSEOUT.md`. The default HTIF loader WFI limitation remains documented but does not alter binary/RTL semantics.
- L2 macro boundaries are frozen, not closed: generated Gemmini is locked at 157 ports (SHA256 `8ae6fd2e...130ce66f0`) with retained RocketTile command router/PTW/TileLink context. `gemmini_rocc_command_adapter` remains a clean-room-only test adapter and must not be connected to the macro.
- The pinned AHA 4x16 `Interconnect` macro was regenerated as SHA256 `4980ce62...0bf0ab354`; its 69 ports and 25-file generated simulator closure passed host Verilator 5.050 complete named-port lint. Native 17-bit data lanes and independent 1-bit EOS lanes must remain separate; do not map `last` into bit 16.
- Current action: extend `src/heteronpu/gemmini_rocc_lowering.py` from exact primitive encoders to typed matrix descriptors and compare emitted sequence against the official C route. The primitive lowering tests pass under `PYTHONPATH=src`.
- `lc_shell` was not found; it is only a future L10 SRAM-library dependency.
- Do not close any stage using the existing clean-room-only evidence.
