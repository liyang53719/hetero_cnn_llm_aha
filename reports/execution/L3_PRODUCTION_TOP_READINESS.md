# L3 production top readiness

Status: production-top subgates PASS; final combined L3 gate remains.

`hetero_l3_production_top` now structurally combines:

- real-SRAM command/event frontend with depth-16 command and completion FIFOs;
- six-engine dispatch, one in-flight command per engine and status-6 watchdog lock;
- seven-input round-robin completion merger;
- four-logical-read/two-logical-write Shared-L2 arbiter;
- pinned Gemmini scratchpad gateway and four direct-stream skid channels;
- production AHA proc-packet and external KV staging endpoints.

Strict project `-Wall` lint passes for the canonical top. A lint-only SRAM port
stub avoids treating vendor timing-model internals as project warnings; every
functional gate compiles the real ARM SRAM model.

Control-plane real-macro regression passes 100,003 commands/completions: 100k
normal commands across all six engines, Event ID 0, one illegal engine status,
one watchdog status-6 lock, and reset recovery. Data-plane regression passes
100k transfers with 150k Matrix gateway completions, 50k AHA round trips and
50k KV write/read operations.

Evidence:

- `scripts/run_l3_command_fabric.sh`
- `work/results/l3_command_fabric/verilator_100k.log`
- `scripts/run_l3_stream_complex.sh`
- `work/results/l3_stream_complex/verilator_100k.log`
- `reports/execution/l3_production_top_readiness_result.json`

L3 is not yet PASS: the final test must run command/event, all Shared-L2 clients
and all four streams concurrently in this canonical top for at least 100k
commands/transactions.
