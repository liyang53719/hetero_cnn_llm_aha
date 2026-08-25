# L3 SRAM-backed event scoreboard

The 16-bit event contract is now implemented with one planned Control/trace
`ctsp4096x128wm` macro instead of 65,536 event flops. Each Event ID owns one
byte: row=`event_id[15:4]`, byte=`event_id[3:0]`. A successful completion writes
one byte through the real macro byte-mask wrapper; waits read the containing
row. Reset deterministically clears all 4096 rows before `init_done` is raised.

The same two-epoch 100,000-command test passes on the real ARM model:

`COMMAND_EVENT_SCOREBOARD_SRAM_100K_PASS commands=100000 success=100000 errors=23 cycles=1158225`

Error completions remain blocking, high Event IDs do not alias, reset clears
the prior epoch, macro errors are zero, and Verilator 5.050 elaborates the
vendor model. The macro Liberty area is 129,080.9927 square microns and is
already part of the fixed Control/trace SRAM budget.

Evidence:

- `rtl/integration/command_event_scoreboard_sram.sv`
- `tb/tb_command_event_scoreboard_sram_100k.sv`
- `scripts/run_l3_event_scoreboard_sram.sh`
- `work/results/l3_event_scoreboard_sram/tb.log`
- `work/results/l3_event_scoreboard_sram/verilator_lint.log`

Production shell connection and DB timing link remain before stage closure.
