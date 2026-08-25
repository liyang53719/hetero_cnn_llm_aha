# L11 execution handoff

- Canonical stages are L0-L11 from `reports/ARCHITECTURE_AND_EXECUTION_PLAN.md`.
- Current phase: L1 upstream reproduction.
- Every compile, simulation, synthesis, and Docker command uses `taskset -c 8-25`; Docker additionally uses `--cpuset-cpus=8-23`.
- L0 PASS: 27 Python tests, C++ reference, RTL contract simulation, and five 1.0 ns CLN22UL contract DC tops passed. The integrated contract top has WNS 9.75132e-05 ns and zero unmapped cells.
- Docker package and group membership are present, but this login has not refreshed the `docker` group. Test Docker with `sg docker -c 'docker version'` or after a new login.
- Docker daemon currently lacks the shell HTTPS proxy; use `scripts/check_docker_proxy.sh` for the user-owned sudo drop-in, then pull a digest-pinned AHA image.
- `scripts/write_used_upstream_lock.py` PASSed. It locks the actual Gemmini and AHA Gaussian/PnR dependency closure and intentionally excludes unrelated Chipyard/ Voyager LFS subtrees.
- Fresh Gemmini evidence: Spike mvin/mvout PASS, Spike OS-matmul PASS, Verilator mvin/mvout PASS (669 us), and Verilator OS-matmul PASS (10 ms, 577.7 s wall).
- Remaining Gemmini baseline failures: Spike ResNet50 exits `tohost=1337`; default matmul timeout is not a PASS.
- `lc_shell` was not found; it is only a future L10 SRAM-library dependency.
- Do not close any stage using the existing clean-room-only evidence.
