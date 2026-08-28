# L5.2 Revision 7 post-synthesis gate comparison plan

## Decision basis

Revision 7 permits either Formality or an approved post-synthesis gate
comparison. No `fm_shell` installation is available on this host. The source
remap lane passed CLN22UL 1.0 ns at WNS `+0.000141501 ns`; equivalence remains
mandatory before E1 or H3 promotion.

## Frozen comparison

- Simulator: VCS W-2024.09, CPU 8-23, `MemoryHigh=24G`, `MemoryMax=30G`.
- Reference sources: pinned emitter-generated SystemVerilog plus unchanged
  `bf16_fma_pipeline_lane.sv` and `bf16_context_fma_pipeline_lane4.sv`.
- Implementation: Revision-7 mapped netlist SHA256
  `23abb9bddd9530e231fc617f59a67637c1e1f9d8ab5dcc867f7da6d804e05d72`.
- Cell model: CLN22UL base-SVT C35 functional Verilog SHA256
  `527f1fe8c867e975926a89478187effdf662ab32d87e286ad6d98267dc1a4d8f`.
- RTL and gate are compiled into separate binaries from the same comparison
  testbench and deterministic stimulus implementation.

The test initializes all four lane-local accumulator contexts through legal
clear/complete operations, then executes:

1. at least 100,000 no-stall dependent operations with four-context rotation
   and same-cycle completion bypass;
2. at least 20,000 deterministic randomized cycles covering stage enables,
   clear, bank select, bypass, completion context, BF16 operands and stalls;
3. drain cycles before final comparison.

Each binary writes one line per sampled cycle containing `out` and exception
flags. Unknown outputs, line-count differences, or any byte mismatch fail.
Success requires identical trace SHA256 values and records binary/source/
netlist/library hashes, seed, cycles and tool version in
`reports/execution/l5_revision7_gate_compare_result.json` with method
`post_synthesis_gate_compare`.

The comparison does not authorize RTL/generated-file edits, retiming, timing
exceptions, a fifth context/cycle, frequency reduction or a flat array build.
Only the generated evidence file may be passed to
`REV7_EQUIVALENCE_EVIDENCE` for the reviewed `equiv` command.
