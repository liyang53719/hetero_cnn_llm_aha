# L5.2 Revision 7 approval

## Decision

`APPROVE_WITH_GATES`.

Revision 7 may remap exactly one reusable four-context BF16 context lane from committed emitter-generated SystemVerilog plus the unchanged handwritten base lane and context-lane RTL. DC may optimize across the lane-local accumulator mux, `bf16_fma_pipeline_lane`, and `HeteroBF16FmaPre` boundary.

This approval is a synthesis-boundary change only. It does not authorize RTL or Scala emitter modification, hand edits to generated SystemVerilog, another context or pipeline cycle, smaller array, lower frequency, synchronous-data false paths, multicycle constraints, register retiming, or a flat 512-lane compile.

## Rationale

Revision 6 maps all generated arithmetic leaf DDCs independently. The remaining path is `issue_bypass_i -> accumulator mux -> HardFloat Pre -> pre_c_q`, so the frozen DDC boundary prevents the only useful local optimization. Normal/high Revision-6 attempts remain at `-0.034333 ns` and `-0.0371628 ns`, with zero unmapped/unresolved references. Mul/Post/Round are not on the critical path.

The requested source remap is therefore the smallest remaining implementation-flow change that preserves the accepted architecture and cycle contract.

## Promotion gates

Revision 7 can replace the failed Revision-6 lane DDC only after:

1. single-lane CLN22UL 1.0 ns WNS is nonnegative;
2. unmapped and unresolved counts are zero;
3. Formality or an approved post-synthesis gate comparison passes;
4. the real 512-lane/four-context E1 is rerun and remains exact;
5. structural H3 contains 512 instances of one accepted context-lane design and passes 1.0 ns timing;
6. final H3 has zero unmapped/unresolved references and no stale report;
7. area delta is recorded; above 10% requires review and above 20% blocks promotion because the lane cost is replicated 512 times.

A lane WNS in `[0, 0.02 ns)` is a marginal component pass and may proceed to H3, but is not physical signoff. L5.2 closes only after H3 and the E1 rerun pass.
