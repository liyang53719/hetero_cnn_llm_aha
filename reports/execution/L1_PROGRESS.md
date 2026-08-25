# L1 progress — 2026-08-25

All reported compile, simulation, and synthesis commands use `taskset -c 8-25`.

Completed:

- The actual Gemmini and AHA Gaussian/PnR dependency closure is exact and clean; see `upstream_closure.json`.
- AHA recursive source checkout is pinned at `3b171e813bc5e399b22921c8df20fd4e889f1569`.
- Bender 0.32.0 is installed under `work/toolchain/bender-0.32.0` and verified against the release SHA256.
- iDMA source enumeration passed from its committed `Bender.lock` with 461 source lines; no `bender update` was performed.
- iDMA upstream-equivalent VCS `tb_idma_backend_rw_axi` completed the documented `simple.txt` job: 3 transfers, 1224 B, 4070 ns `$finish`, and a DMA trace artifact.
- Gemmini official `mvin_mvout` passed on Spike and Verilator.
- Gemmini official `matmul_os` passed on Spike and Verilator. The fresh Verilator run reached `$finish` at 10 ms in 577.680 s.
- Gemmini official `resnet50-baremetal os` passed on Spike in 3,053,813 cycles with all four predictions reported and a final `PASS`.
- A five-minute commit-trace diagnostic observed continuous Gemmini operations without a trap or mismatch; it timed out by design and is not used as pass evidence.
- AHA 4x16 generated RTL, Gaussian map and PnR, bitstream, and test are complete on the pinned image source using VCS W-2024.09. The test reports `PASS` and an integer bit-accurate output comparison; simulated time is 14,727,500 ps. This is equivalent simulator evidence, not the formal Verilator subgate.
- A fresh canonical `matmul_ws-baremetal` Verilator run reached the unchanged 10,000,001-cycle TestDriver timeout without mismatch output. The old 20M `$finish` log lacks a captured command and binary hash, so it cannot be used to claim WS PASS; see `L1_GEMMINI_WS_AUDIT.md`.
- AHA 4x16 formal Verilator closure now passes with source-locked Verilator 5.028, GCC10 C++20 coroutine support, and the pinned image source. The full Gaussian Vtop run reports `PASSED`, and the final output comparison is integer bit-accurate; see `work/results/l1_aha_verilator_5028_cxx10_makeflags/result.json` and `reports/execution/aha_verilator_result_audit.json`.
- The WS timeout is now localized before firmware execution: a 1M-cycle standard-runner trace executes 14 boot instructions then remains at boot ROM `wfi`; an mvin control run reaches 22,343 commits and PASSes in the same simulator. See `L1_GEMMINI_WS_BOOT_AUDIT.md`; no cycle-budget expansion is permitted.

Open L1 gates:

- Canonical N=2 Gemmini WS boot-handoff repair. The fixed 10M-cycle attempt has no firmware progress counter because it never leaves boot ROM WFI; policy prohibits increasing its budget. The combined default workload's historical 20M timeout remains a failure.

The Gemmini documentation explicitly notes that large DNN binaries are not practical for Verilator/VCS. The CNN functional baseline is therefore a Spike gate; RTL evidence is retained for mvin/mvout and matmul.
