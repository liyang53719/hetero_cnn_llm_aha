# L2 Gemmini mvin/mvout edge equivalence

One unmodified `GemminiRocketConfig` ran official and raw-lowered paths for
1x1, 1x16, 16x1, 15x16, and 16x15 shapes with unaligned DRAM starts and
24-byte row stride. It also covered INT32 accumulator input with both scaled
INT8 output and full-width INT32 output.

Result: PASS. The 60 Rocket CUSTOM_3 commits match the Python command
encoders; official/raw pairs differ only at seven intentional mvout
destinations. Every payload is bit-exact; checksum is `822510027983880976`.
Verilator completed at 107 us using 285 MB.

Evidence:

- `tests/gemmini_l2_mvin_mvout_edges_equivalence.c`
- `scripts/audit_gemmini_l2_mvin_mvout_edges.py`
- `work/results/l2_gemmini_rocc_equiv/mvin_mvout_edges_result.json`
- `work/results/l2_gemmini_rocc_equiv/verilator_mvin_mvout_edges.log`
