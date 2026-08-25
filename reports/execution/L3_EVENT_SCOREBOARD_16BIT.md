# L3 16-bit event scoreboard readiness

The event scoreboard now implements the frozen 16-bit Event ID contract rather
than the legacy low-eight-bit subset. Event ID zero means no wait; successful
completion marks an ID persistent until reset, while nonzero completion status
does not release the dependency. Runtime must allocate unique IDs within each
reset epoch.

The deterministic randomized-backpressure regression runs two reset epochs:
the first covers IDs 1–65535 and the second adds 34,465 commands, for 100,000
accepted commands and 100,000 successful completion events. Twenty-three
error completions are injected before their matching success and are proven
not to release waiting commands. Result:

`COMMAND_EVENT_SCOREBOARD_100K_PASS commands=100000 success=100000 errors=23 cycles=218280`

Payload mismatch, premature release, high-ID alias, loss, timeout, and reset
leakage are zero. Verilator 5.050 lint passes. The current 65,536-bit bitmap is
a functional L3 implementation; L10 may map or pipeline it using Control/trace
SRAM if flop area is excessive, without changing event semantics.

Evidence:

- `rtl/integration/command_event_scoreboard.sv`
- `tb/tb_command_event_scoreboard_100k.sv`
- `scripts/run_l3_event_scoreboard.sh`
- `work/results/l3_event_scoreboard/tb.log`
- `work/results/l3_event_scoreboard/verilator_lint.log`

Production engine completion integration and the L2 dependency remain before
L3 PASS.
