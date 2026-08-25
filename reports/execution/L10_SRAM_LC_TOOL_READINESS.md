# L10 SRAM and Library Compiler readiness

This is early readiness evidence only. L10 remains PENDING behind L2–L9.

Installed and verified:

- Design Compiler X-2025.06-SP3.
- ARM CLN22UL SP SRAM compiler `sram_sp_hde_svt_mvt` r0p0.
- ARM CLN22UL UHDE SP SRAM compiler `sram_sp_uhde_svt_mvt` r1p0.
- ARM CLN22UL DP SRAM compiler `sram_dp_hde_svt_svt` r0p1.
- UHDE SP `6144x128`, mux8, BASE, 0.8 V TT25 generates successfully.
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
5. The HDE SP delivery does not provide the requested BASE 0.8 V TT25
   combination for this shape, but the installed UHDE SP r1p0 delivery does;
   no SP corner relaxation is required.
6. Actual bit-write UHDE SP Liberty, Verilog, and GDS2 views are generated and
   validated, and the real macro model passes its production wrapper test, but
   this delivery's `lef-fp` generator fails. A directory-wide audit found no
   pre-generated memory-macro LEF or DB; only compiler-internal `std.db` files.
   All ten installed memory compilers share the same `bifrun` binary (SHA256
   `bb2cd8a8fab1e791eb6404ee4a10c6747efc19a566498380117f35a6b9245d68`).
   File-level tracing proves the generated temporary BIF is opened and then
   `bifrun` terminates with SIGSEGV. GDB identifies
   `Module::ReplaceDummyPinsWithObs()` as the failing frame. Older libstdc++,
   process-local no-ASLR, Ubuntu 18/glibc 2.27, r1p0/r3p1 compilers, and
   `site_def` variants do not fix it. This is a shared delivery/runtime
   defect, not a macro-shape error. The independent GDS2 generator works and
   has produced the real 6144x128 layout.

Required decisions/dependencies:

- Install a licensed Synopsys Library Compiler matching X-2025.06-SP3.
- Approve a DP physical decomposition and VT mode. The validated local option
  is LL at 0.8 V TT25: two `2048x64` macros per logical `2048x128`, and four
  `4096x32` macros per logical `4096x128`.
- Use the validated UHDE SP r1p0 compiler for BASE 0.8 V TT25 SP macros.

Evidence is under `work/results/l10_tool_readiness/`, including compiler help,
dimension probes, DC version, and the failed Liberty-to-DB probe.
