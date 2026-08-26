# L4 INT8 GEMM payload RTL

Status: payload RTL PASS; canonical L3 trace metrics remain, so the INT8 GEMM
subgate and L4 remain `IN_PROGRESS`.

The 17x18x19 output-stationary case executes only the 36-command
production-lowered path in the retained pinned Gemmini/RocketTile RTL. Every
one of 306 INT8 outputs matches an independent NumPy integer golden. The output
SHA256 is `1d3777b3d32a04238220dc560028765d13e1594e48548a658ac80b3e2c9930d5`.

Measured around the first configuration command through Gemmini fence:

- RTL payload cycles: 955;
- exact mvin/mvout requested bytes: 2,195;
- useful MACs: 5,814;
- physical pinned 16x16 peak: 256 MAC/cycle;
- useful end-to-end utilization: 2.3781086%;
- numerical checksum: 14853676686976657775;
- ELF SHA256: `a478b30ecc15aa654d16ac84871b7c41d77ac94d0deb62858fb7c97ae308f0bd`.

The Python lowerer matches all 36 committed CUSTOM_3 funct/rs1/rs2 payloads.
These cycles are actual retained-Gemmini RTL `mcycle`, not an analytical model.
The DMA-byte count is derived from the exact emitted command shapes. Bank
conflicts and canonical L3 trace cycles are intentionally null until the same
trace is replayed through `hetero_l3_production_top`.

Evidence:

- `tests/gemmini_l4_int8_gemm.c`
- `scripts/run_l4_int8_gemm_payload.sh`
- `scripts/audit_l4_int8_gemm.py`
- `work/results/l4_int8_gemm/int8_gemm.log`
- `work/results/l4_int8_gemm/int8_gemm.trace`
- `reports/execution/l4_int8_gemm_payload_result.json`
