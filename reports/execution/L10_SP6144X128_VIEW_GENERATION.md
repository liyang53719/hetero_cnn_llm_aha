# L10 SP 6144x128 view generation

The installed ARM CLN22UL UHDE SP compiler r1p0 generated the first required
production SRAM macro at BASE, 0.8 V, TT25. Bit-write mask is enabled so the
wrapper can preserve the frozen byte-enable contract:

- Liberty: `l2sp6144x128wm_tt_typical_0p80v_0p80v_25c.lib`, SHA256
  `b2f8678b1bf7dc5b1378777b4b130d664649583c817fbafec89ed95144ceeb85`.
- Verilog: `l2sp6144x128wm.v`, SHA256
  `b6928df6a9aaada8efce7759088e680cc5279cb8db538311bf106507845cf7ff`.
- GDS2: `l2sp6144x128wm.gds2`, SHA256
  `d8220179cf3beda7ecc57e7e1c77e9fa82aeac4b8654ecc913a0eb8b60730bbc`.

The audit confirms 6144 words, 128-bit width, 13-bit address, nominal 0.8 V,
and 25 C. Icarus elaborates the generated macro successfully. The compiler's
independent GDS2 path also completes. Proprietary
views remain only under `work/generated` and are not committed.

The earlier no-write-mask macro is superseded and is not a production SRAM
candidate.

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
