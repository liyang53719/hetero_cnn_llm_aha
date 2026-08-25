# L11 execution handoff

- Canonical plan: `reports/ARCHITECTURE_AND_EXECUTION_PLAN.md`; current stage L2.
- CPU rule: all build/test/DC use `taskset -c 8-25`; Docker uses `--cpuset-cpus=8-23`.
- Resource rule: `MemAvailable > 10 GiB`, at most `-j4`, user/Docker memory cap required.
- L0 PASS; L1 upstream PASS.
- AHA L2 PASS: pinned 4x16 Garnet, official control/input transcript, full input readback, G2F/F2G ISR, and both output blocks bit-exact; 19,914 cycles on Verilator 5.028. Evidence: `work/results/l2_aha_garnet_full_numerical.log`.
- Official test_app trace independently PASSes and its first output word matches wrapper/golden `0x00710070006d0070`.
- L2 remains IN_PROGRESS only for Gemmini retained-RocketTile descriptor->RoCC/C/RTL write/event/numerical equivalence.
- Next action is exactly `reports/execution/NEXT_ACTION.json`.
- Future L10 blocker: `lc_shell` not yet found for SRAM `.lib` to `.db` conversion.
- Do not close a stage with clean-room-only evidence.
