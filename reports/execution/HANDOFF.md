# L11 execution handoff

- Canonical plans: `reports/ARCHITECTURE_AND_EXECUTION_PLAN.md` and `reports/L2_TO_L11_DECISION_COMPLETE_EXECUTION_PLAN.md`.
- Gates: L0 PASS, L1 PASS, L2 PASS, L3 IN_PROGRESS, L4-L11 dependency-blocked.
- L2: Descriptor/ISA v2, Gemmini OS/WS/Conv/bias/requant production path, AHA Gaussian wrapper, and KV/iDMA basic path are closed by `gate/L2-pass` (`abe2c70`).
- L3 Shared-L2: 16 real ARM macros, 4 logical reads to 2R, 2 logical writes to 1W, descriptor promotion, byte enables and 100k+ contention tests PASS.
- L3 control: command FIFO 16, completion FIFO 16 and real 4096x128 event SRAM pass 100k commands; error completion never releases a wait event.
- L3 streams: four skid channels and gateway pass 100k; four emitted pinned upstream `ScratchpadBank(4096x128)` instances then pass a second 100k through real write/read/fromDMA queues and ExtMemIO. Hash `c65a53d9...`, upstream clean.
- Current limitation: AHA/KV production stream endpoints and combined L3 regression remain.
- Failed route retired: full-chip direct-extmem firtool exceeded the project 10 GiB cap once and later hit a CIRCT `SmallVector` fault. Do not retry or raise the cap.
- Next: implement `aha_tensor_stream_endpoint` around the existing proc-packet writer and `kv_tensor_stream_endpoint` around 512 KiB staging, then connect channels 0/1 and 2/3 respectively.
- L10 readiness only: ARM Liberty/Verilog/GDS2 and wrappers exist; official `.db/LEF` remain deferred, so L10/L11 cannot PASS.
- Resource contract: every build/test/DC uses `taskset -c 8-25`, max `-j4`, starts only with `MemAvailable >10 GiB`, and uses a 10 GiB cgroup cap.
- Never add user files `scripts/prepare_aha_ast_tools_runtime.sh` or `scripts/prepare_aha_halide_runtime.sh`.
