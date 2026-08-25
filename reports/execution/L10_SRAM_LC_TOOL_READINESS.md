# L10 SRAM and Library Compiler readiness

This is early readiness evidence only. L10 remains PENDING behind L2–L9.

Installed and verified:

- Design Compiler X-2025.06-SP3.
- ARM CLN22UL SP SRAM compiler `sram_sp_hde_svt_mvt` r0p0.
- ARM CLN22UL DP SRAM compiler `sram_dp_hde_svt_svt` r0p1.
- SP `6144x128`, mux8, BASE passes compiler dimension validation.
- DP LL 0.8 V TT25 alternatives `2048x64`, mux8 and `4096x32`, mux16
  both generate datatables successfully.

Blocking incompatibilities with the fixed L10 plan:

1. Library Compiler is not installed. DC exposes `read_lib/write_lib`, but a
   real conversion fails with `LCSH-3: Check the installation of Library
   Compiler`. No local LC installer was found.
2. The delivered DP compiler rejects `-mvt BASE`.
3. At 128-bit width (mux4), DP depth is limited to 1024; direct `2048x128`
   and `4096x128` are rejected.
4. The plan's same-depth two-64-bit fallback is feasible for 2048 depth, but
   4096 depth requires four `4096x32` macros or depth splitting.
5. SP `6144x128 BASE` succeeds at its supported corners, but explicit 0.8 V
   TT25 generation is unavailable in this configuration; its successful
   default datatables include 0.9 V TT25 instead.

Required decisions/dependencies:

- Install a licensed Synopsys Library Compiler matching X-2025.06-SP3.
- Approve a DP physical decomposition and VT mode. The validated local option
  is LL at 0.8 V TT25: two `2048x64` macros per logical `2048x128`, and four
  `4096x32` macros per logical `4096x128`.
- Either approve SP LL/another compiler for 0.8 V, or approve BASE at its
  supported 0.9 V TT25 corner. Do not silently relabel either as BASE 0.8 V.

Evidence is under `work/results/l10_tool_readiness/`, including compiler help,
dimension probes, DC version, and the failed Liberty-to-DB probe.
