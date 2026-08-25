# L2 Gemmini multi-tile OS equivalence

The pinned 17x18x19 INT8+bias case executes as 2x2x2 Gemmini tiles with tail
padding 15/14/13. One unmodified `GemminiRocketConfig` runs official
`tiled_matmul` and the project raw lowering against the same A/B/D inputs.

Result: PASS. Each path commits 36 CUSTOM_3 commands. All funct3, funct7,
rs1, and rs2 fields match except the four intentional mvout destination-array
addresses. The audit independently instantiates `lower_int8_os_tiles` and
matches all 36 raw Rocket commits. Official, lowered, and CPU-golden matrices
are bit-exact; checksum is `14853676686976657775`. Verilator completed at
191 us using 285 MB.

Evidence:

- `tests/gemmini_l2_multi_tile_os_equivalence.c`
- `scripts/audit_gemmini_l2_multi_tile_os_equivalence.py`
- `work/results/l2_gemmini_rocc_equiv/multi_tile_os_result.json`
- `work/results/l2_gemmini_rocc_equiv/verilator_multi_tile_os.log`
