# L3 production fabric closeout

Status: PASS.

Dependency L2 is PASS. The canonical L3 top is
`rtl/integration/hetero_l3_production_top.sv`; it contains the queued real-SRAM
event frontend, fair completion merge, watchdog, four-read/two-write logical L2
arbiter, pinned Gemmini scratchpad gateway, four stream skids and production
AHA/KV endpoints.

The final concurrent gate ran one canonical top and one clock/reset domain with:

- 100,003 accepted host commands and 100,003 completions;
- all six engine command/completion interfaces progressing with exact counts;
- Event ID 0, one illegal-engine status 1 and one watchdog status 6;
- 100,002 Shared-L2 transactions: 51,313 reads, 48,689 writes and 51,313 exact responses;
- all four logical read clients and both logical write clients progressing;
- 1,099 descriptor promotions after the fixed eight-cycle threshold;
- 10,000 direct-stream operations and 15,000 Matrix gateway completions;
- 5,000 AHA round trips and 5,000 KV operations over all four channels;
- 8,524 bank conflicts, 4,084 read stalls and 4,440 write stalls, proving concurrent contention;
- zero numerical mismatch, loss, duplication, reorder, starvation, protocol error,
  macro error, assertion or timeout.

The combined gate uses the cycle-equivalent physical Shared-L2 model behind the
production arbiter so ownership and contention are observable. The identical
2R+1W physical interface is separately closed against all 16 generated ARM
6144x128 macros by the existing 100k macro-fabric gate. The combined event path
does compile and run the real ARM 4096x128 Control SRAM model. Pinned Gemmini
`ScratchpadBank` RTL, AHA proc-packet behavior and upstream iDMA/KV behavior are
covered by their production subgates; no `engine_contract_adapter` result is
used as Matrix/SFU/KV closure evidence.

Additional directed gates prove nonzero-status completions never release wait
events, successful Event ID 0 does not write the scoreboard, host ready remains
low during SRAM initialization, and watchdog reset clears the lock. Strict
project Verilator `-Wall` lint is clean. Vendor SRAM timing-model warnings are
isolated from project lint by a port-only lint stub; functional tests use the
real vendor models.

Primary evidence:

- `scripts/run_l3_production_top_combined.sh`
- `work/results/l3_combined/verilator_lint.log`
- `work/results/l3_combined/verilator_100k.log`
- `reports/execution/l3_closeout_result.json`
- `work/results/l3_macro_fabric/tb.log`
- `work/results/l3_event_scoreboard_sram/tb.log`
- `work/results/l3_spad_gateway/pinned_100k.log`
- `work/results/l3_aha_kv_endpoints/tb_100k.log`

L3 PASS does not claim the L4 production 4x4 AHA/Lake SFU, CNN numerical cases,
L5 BF16 array, advanced KV, or any L10/L11 timing result.
