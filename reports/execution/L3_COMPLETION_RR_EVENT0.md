# L3 completion fairness and Event 0

Status: readiness subgate PASS; L3 remains `IN_PROGRESS`.

The fixed-priority completion merge has been replaced for the production top by
`engine_completion_rr_arbiter`. Six engine completion inputs plus one synthetic
watchdog/error input are registered and served round-robin. Output valid/data
remain stable until accepted.

Verilator 5.050 passed 100,000 saturated completions with exact per-source
ordering and no starvation; each source received 14,285 or 14,286 grants.
Strict `-Wall` is clean.

The real-SRAM event scoreboard now consumes successful Event ID 0 without
writing row 0. Its original two-reset 100,000-command real ARM macro regression
was rerun unchanged and passed: 100,000 commands, 100,000 successful events, 23
error completions, zero macro errors.

Evidence:

- `scripts/run_l3_completion_rr.sh`
- `work/results/l3_completion_rr/verilator_100k.log`
- `scripts/run_l3_event_scoreboard_sram.sh`
- `work/results/l3_event_scoreboard_sram/tb.log`
