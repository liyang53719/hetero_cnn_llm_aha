# L2 Gemmini CUSTOM_3 program adapter control gate

The legacy command adapter is not a valid Gemmini macro path: it emits
CUSTOM_0 and waits for a generic response. A new
`gemmini_rocc_program_adapter` accepts validated first/last-tagged CUSTOM_3
micro-ops, propagates ready/valid backpressure, preserves payload order, and
completes only after the final command is accepted and Gemmini busy asserts
then clears. An illegal first packet emits status 1 without issuing RoCC.

Directed randomized-ready RTL result: PASS. Two legal programs issued 15
commands in order and generated exactly two success events. One illegal
program issued zero commands and generated exactly one error event. The
completion scoreboard field decode was corrected to the frozen
`{event_id,status,engine,counter}` layout. Icarus, Verilator 5.050 lint, the
full open-RTL regression, structural checks, and the immutable Gemmini/Rocket
boundary audit all pass.

Evidence:

- `rtl/integration/gemmini_rocc_program_adapter.sv`
- `tb/tb_gemmini_rocc_program_adapter.sv`
- `tb/tb_command_event_scoreboard.sv`
- `work/results/l2_gemmini_control/program_adapter.log`
- `work/results/l2_gemmini_control/scoreboard.log`
- `work/results/l2_gemmini_control/open_rtl_verilator_gate.log`
- `work/results/l2_gemmini_control/macro_boundary_result.json`

This is an adapter contract gate, not final L2 closure. The production
integration still instantiates the legacy adapter; a descriptor sequencer must
connect the new program adapter.

A simulation-only bind monitor was also compiled into an independent debug
build of the unmodified retained RocketTile. Across the four conv programs it
observed all 36 expected Gemmini commands and, after each final funct-15
command, a real Gemmini busy-active interval ending in busy clear. Numerical
checksum remained unchanged. Evidence is
`work/results/l2_gemmini_control/retained_busy_result.json`.
