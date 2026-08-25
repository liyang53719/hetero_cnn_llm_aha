# L2 Gemmini retained-Rocket equivalence

The pinned 3x7x5 INT8 output-stationary descriptor was executed twice in one
unmodified `GemminiRocketConfig` simulator: once through official Gemmini C
macros and once through raw CUSTOM_3 payloads matching
`gemmini_rocc_lowering.py`.

Result: PASS. Each path commits 11 CUSTOM_3 commands. The first ten commands
have identical funct3/funct7/rs1/rs2 payloads. Final `mvout` differs only in
the expected destination (`C_macro=0x80002b50`, `C_raw=0x80002b60`) and shares
the same local-address/shape rs2. Both paths and the CPU golden are bit-exact;
checksum is `6954858531263039530`.

Evidence:

- `tests/gemmini_l2_rocc_equivalence.c`
- `scripts/audit_gemmini_l2_equivalence.py`
- `work/results/l2_gemmini_rocc_equiv/result.json`
- `work/results/l2_gemmini_rocc_equiv/verilator.log`

This closes only resolved single-tile OS descriptor equivalence. L2 still
requires multi-tile/WS, conv/bias/requant, backpressure, event, and illegal
descriptor coverage in retained RocketTile context.
