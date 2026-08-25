# L11 execution handoff

- Canonical stages are L0-L11 from `reports/ARCHITECTURE_AND_EXECUTION_PLAN.md`.
- Current phase: L1 upstream reproduction.
- Every compile, simulation, synthesis, and Docker command uses `taskset -c 8-25`; Docker additionally uses `--cpuset-cpus=8-23`.
- L0 PASS: 27 Python tests, C++ reference, RTL contract simulation, and five 1.0 ns CLN22UL contract DC tops passed. The integrated contract top has WNS 9.75132e-05 ns and zero unmapped cells.
- Docker package and group membership are present, but this login has not refreshed the `docker` group. Test Docker with `sg docker -c 'docker version'` or after a new login.
- Docker daemon currently lacks the shell HTTPS proxy; use `scripts/check_docker_proxy.sh` for the user-owned sudo drop-in, then pull a digest-pinned AHA image.
- Current gate status: `BLOCKED_DOCKER_PROXY`. `systemctl show docker --property=Environment` is empty and `docker pull hello-world:latest` times out at `registry-1.docker.io`.
- `scripts/write_used_upstream_lock.py` PASSed. It locks the actual Gemmini and AHA Gaussian/PnR dependency closure and intentionally excludes unrelated Chipyard/ Voyager LFS subtrees.
- Fresh Gemmini evidence: Spike mvin/mvout PASS, Spike OS-matmul PASS, Verilator mvin/mvout PASS (669 us), and Verilator OS-matmul PASS (10 ms, 577.7 s wall).
- Spike ResNet50 also passes in explicit `os` mode: 3,053,813 cycles and final `PASS`. The previous `tohost=1337` was a default WS-mode run, not an architectural functional mismatch.
- The default combined matmul timeout remains a failure; standalone OS and WS variants have passing evidence.
- `lc_shell` was not found; it is only a future L10 SRAM-library dependency.
- Do not close any stage using the existing clean-room-only evidence.
