# L1 Gemmini WS boot-handoff audit — 2026-08-25

## Purpose

Determine whether the canonical N=2 `matmul_ws-baremetal` timeout represents
ongoing workload execution (which could justify one bounded budget expansion)
or a pre-workload failure.

## Controlled 1M-cycle traces

Both runs used the same pinned `GemminiRocketConfig` simulator, DRAMSim2
configuration, `taskset -c 8-25`, and the official standard `run-binary`
path with `+verbose` and `spike-dasm` hardware commit decoding.

| Binary | Terminal | Commit records | Observation |
|---|---:|---:|---|
| `mvin_mvout-baremetal` | PASS at 668,756 cycles | 22,343 | reaches `0x80000000`, emits 583 custom/Gemmini matches |
| `matmul_ws-baremetal` | timeout at 1,000,001 cycles | 14 | reaches `wfi` at cycle 54 and makes no later commit |

The WS trace is at
`work/upstream/chipyard_gemmini/sims/verilator/output/chipyard.harness.TestHarness.GemminiRocketConfig/matmul_ws-baremetal.ws_progress_1m.out`.
The mvin control trace is the adjacent
`mvin_mvout-baremetal.mvin_progress_1m.out`.

## ELF comparison

The working mvin and stalled WS binaries have the same executable entry point
`0x80000000`, `tohost` at `0x80001000`, `fromhost` at `0x80001040`, and zeroed
tohost data. WS is only modestly larger (27,193 bytes vs 7,431 bytes in ELF
text/data/bss accounting); this does not explain a 64-bit address or segment
mapping mismatch.

## Conclusion

The canonical WS binary is stalled before its firmware executes. This is a
**boot-handoff / interrupt release failure**, not a running Gemmini workload,
numerical mismatch, or bandwidth/compute timeout. There is no continual
progress counter, so the execution contract forbids increasing the 10M-cycle
budget to 20M. `FAST=1` and historical unproven logs cannot substitute for
this full N=2 gate.

L1 stays open until the exact upstream boot-handoff discrepancy is repaired
without modifying the canonical AHA/Gemmini workload contract.
