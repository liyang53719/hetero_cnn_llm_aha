# L2 Gemmini multi-tile WS equivalence

The pinned 17x18x19 INT8 case executes as 2x2x2 Gemmini tiles with tail
padding 15/14/13. It was run twice in one unmodified
`GemminiRocketConfig`: first through official `gemmini_loop_ws`, then through
the six raw CUSTOM_3 payloads emitted by the project lowerer.

Result: PASS. Each path commits five identical execute/load/store setup
commands followed by funct 9/10/11/12/13/8. Every command payload matches
except the deliberately distinct output DRAM address. Official, lowered, and
CPU-golden matrices are bit-exact; checksum is `14853676686976657775`.
Verilator completed at 198 us using 285 MB.

Evidence:

- `tests/gemmini_l2_loop_ws_equivalence.c`
- `scripts/audit_gemmini_l2_loop_ws_equivalence.py`
- `work/results/l2_gemmini_rocc_equiv/loop_ws_result.json`
- `work/results/l2_gemmini_rocc_equiv/verilator_loop_ws.log`

The first failed attempt exposed a real harness error: `gemmini_loop_ws` only
emits loop commands and requires the configuration performed by upstream
`tiled_matmul_outer`. Adding that exact setup removed the TileLink assertion;
no upstream source or RTL was changed.
