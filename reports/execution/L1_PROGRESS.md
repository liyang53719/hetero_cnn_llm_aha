# L1 progress — 2026-08-25

All reported compile, simulation, and synthesis commands use `taskset -c 8-25`.

Completed:

- The actual Gemmini and AHA Gaussian/PnR dependency closure is exact and clean; see `upstream_closure.json`.
- AHA recursive source checkout is pinned at `3b171e813bc5e399b22921c8df20fd4e889f1569`.
- Bender 0.32.0 is installed under `work/toolchain/bender-0.32.0` and verified against the release SHA256.
- iDMA source enumeration passed from its committed `Bender.lock` with 461 source lines; no `bender update` was performed.
- Gemmini official `mvin_mvout` passed on Spike and Verilator.
- Gemmini official `matmul_os` passed on Spike and Verilator. The fresh Verilator run reached `$finish` at 10 ms in 577.680 s.
- Gemmini official `resnet50-baremetal os` passed on Spike in 3,053,813 cycles with all four predictions reported and a final `PASS`.
- A five-minute commit-trace diagnostic observed continuous Gemmini operations without a trap or mismatch; it timed out by design and is not used as pass evidence.

Open L1 gates:

- Docker daemon proxy configuration, then immutable AHA image pull and 4x16 Gaussian generation/map/PnR/test.
- Full default/weight-stationary Gemmini workload budget closure; existing 20M-cycle default timeout remains a failure.
- iDMA upstream-equivalent VCS backend read/write job.

The Gemmini documentation explicitly notes that large DNN binaries are not practical for Verilator/VCS. The CNN functional baseline is therefore a Spike gate; RTL evidence is retained for mvin/mvout and matmul.
