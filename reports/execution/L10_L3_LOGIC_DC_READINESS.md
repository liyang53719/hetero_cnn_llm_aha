# L10 DC readiness for new L3 logic

Both new L3 logic blocks were synthesized with Design Compiler X-2025.06-SP3,
CLN22UL 6.5-track BASE SVT 0.8 V TT25, 1.0 ns clock, 0.08 ns uncertainty,
0.10 ns I/O budgets, and four DC cores.

| Top | WNS ns | Unmapped | Total cell area |
|---|---:|---:|---:|
| `matrix_direct_streams` | +0.0162122 | 0 | 5,832.007992 |
| flop `command_event_scoreboard` reference | 0.0 | 0 | 177,205.846133 |

The direct streams meet 1 GHz. The functional flop bitmap technically maps and
meets with zero margin, but its 63,894.103945 combinational and 113,311.742188
noncombinational area plus roughly 28-minute compile time make it a rejected
production implementation. It is retained only as an executable semantic
reference. The production scoreboard is the SRAM-backed version proven in
`L3_EVENT_SCOREBOARD_SRAM.md`; final DC timing awaits the SRAM `.db` dependency.

Evidence:

- `scripts/run_l10_dc_l3_logic.sh`
- `work/results/l10_dc_readiness/matrix_direct_streams/status.txt`
- `work/results/l10_dc_readiness/matrix_direct_streams/area_hier.rpt`
- `work/results/l10_dc_readiness/command_event_scoreboard/status.txt`
- `work/results/l10_dc_readiness/command_event_scoreboard/area_hier.rpt`

This is component readiness, not L10 PASS.
