# Local Agent execution guide v4

1. Start from a clean `main` worktree and run `./scripts/sandbox_validate.sh`.
2. Read `config/control_plane.json`, `reports/execution/NEXT_ACTION.json` and
   `reports/execution/LOCAL_AGENT_WAITLIST.json` before changing RTL.
3. Use `taskset -c 8-23`, at most eight build cores, four simulation threads per
   process and the existing 30 GiB memory cap.
4. L5.1 requires Verilator/VCS, generated FP primitives and CLN22UL DC. Close
   all 132 vectors, random backpressure and early 1 GHz DC in one commit.
5. L5.2 must use lane-local accumulator context banks in the real 512-lane BF16
   array; `matrix_context_scoreboard.sv` is only a protocol seed.
6. L8.1 may run in parallel: obtain the frozen Qwen3.8 files and capture official
   node/state traces. Trace capture is not RTL support.
7. Implement L8 in the fixed order GDN -> QSA -> GR/PLE -> MoE/MTP -> official
   text closure. Preserve CPU fallback for every backend until its own E1/E2
   gate passes.
8. Every recoverable push includes implementation, result JSON,
   `MASTER_LEDGER.json`, `NEXT_ACTION.json` and `HANDOFF.md`.
9. Never label source readiness as E1, a service replay as E3, or analysis as
   measured cycles. Descriptor records 0x13-0x19 remain status 4 until the
   corresponding backend closes.
