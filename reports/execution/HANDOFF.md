# L11 execution handoff

- Canonical plans: `reports/ARCHITECTURE_AND_EXECUTION_PLAN.md` and `reports/L2_TO_L11_DECISION_COMPLETE_EXECUTION_PLAN.md`.
- Gates: L0 PASS, L1 PASS, L2 PASS, L3 IN_PROGRESS, L4-L11 dependency-blocked.
- L2: Descriptor/ISA v2, Gemmini OS/WS/Conv/bias/requant production path, AHA Gaussian wrapper, and KV/iDMA basic path are closed by `gate/L2-pass` (`abe2c70`).
- L3 Shared-L2: 16 real ARM macros, 4 logical reads to 2R, 2 logical writes to 1W, descriptor promotion, byte enables and 100k+ contention tests PASS.
- L3 control: command FIFO 16, completion FIFO 16 and real 4096x128 event SRAM pass 100k commands; error completion never releases a wait event.
- L3 streams: four skid channels and the four-bank Gemmini scratchpad to 512-bit stream gateway pass 100k transfers; both SFU/KV routes and backpressure covered, Verilator `-Wall` clean.
- Current limitation: gateway is not yet bound to emitted pinned-Gemmini external-scratchpad RTL; AHA/KV production endpoints and combined L3 regression remain.
- Failed route retired: full-chip direct-extmem firtool exceeded the project 10 GiB cap once and later hit a CIRCT `SmallVector` fault. Do not retry or raise the cap.
- Next: emit a lightweight pinned upstream `ScratchpadBank(4096,128,1,false,true,false)` harness, connect it to the gateway, and prove ready/valid behavior before endpoint composition.
- L10 readiness only: ARM Liberty/Verilog/GDS2 and wrappers exist; official `.db/LEF` remain deferred, so L10/L11 cannot PASS.
- Resource contract: every build/test/DC uses `taskset -c 8-25`, max `-j4`, starts only with `MemAvailable >10 GiB`, and uses a 10 GiB cgroup cap.
- Never add user files `scripts/prepare_aha_ast_tools_runtime.sh` or `scripts/prepare_aha_halide_runtime.sh`.
