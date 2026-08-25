# L10 SP 6144x128 view generation

The installed ARM CLN22UL UHDE SP compiler r1p0 generated the first required
production SRAM macro at BASE, 0.8 V, TT25:

- Liberty: `l2sp6144x128_tt_typical_0p80v_0p80v_25c.lib`, SHA256
  `96f9591caf154133b01c65732116fe522e105b32cca8a988755856a5f859d129`.
- Verilog: `l2sp6144x128.v`, SHA256
  `d697b8949079976749ddb5c38c0ecee51eb943b0a15131aadc3cb24c228d9dcc`.
- GDS2: `l2sp6144x128.gds2`, SHA256
  `fab1f3fcf736e205ed22d96a245946b87eabddcec65c877d0eaee45fdc85dd73`.

The audit confirms 6144 words, 128-bit width, 13-bit address, nominal 0.8 V,
and 25 C. Icarus elaborates the generated macro successfully. The compiler's
independent GDS2 path also completes. Proprietary
views remain only under `work/generated` and are not committed.

Status is PARTIAL, not PASS:

- `lef-fp` reaches the shared ARM `bifrun` utility, which SIGSEGVs after
  opening a valid generated BIF. GDB resolves the crash to
  `Module::ReplaceDummyPinsWithObs()` called by `GenNonPoroObsSPin()`.
  Every installed memory compiler contains the identical binary; Ubuntu 18,
  older libstdc++, process-local no-ASLR, r1p0/r3p1, and site-definition
  probes also fail. The public frontend does not permit disabling diode/dummy
  handling, and no modified BIF/LEF is accepted as production evidence.
- Liberty-to-DB remains blocked by missing Synopsys Library Compiler (`LCSH-3`).

Machine-readable evidence:
`work/results/l10_tool_readiness/sp6144x128_views_result.json`.
