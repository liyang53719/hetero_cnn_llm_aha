# Canonical architecture and execution plan v6.2

## Accepted evidence

- L5.1 Block128 E1 and component E4 accepted. CLN22UL 1.0 ns WNS is `+0.0000136495 ns`; this has effectively zero engineering margin and is not post-route/variation signoff.
- L5.2 Matrix context real 16x32/512-lane E1 accepted. Four contexts sustain 1,000,000 dependent issues in 1,000,000 issue cycles; 10,000 random-backpressure operations pass.
- Structural array, scheduler and context broadcast pass component timing.

## Current critical path

Revision 6 leaves the single context lane at `-0.034333 ns` normal and `-0.0371628 ns` high effort. The path crosses `issue_bypass_i`, the lane-local accumulator mux, and HardFloat Pre before `pre_c_q`. Preserving the generated Pre DDC prevents optimization across the only remaining critical boundary.

## Revision 7 decision

Revision 7 is approved with gates. One reusable four-context lane may be remapped directly from pinned emitter-generated SystemVerilog and unchanged handwritten lane RTL. DC may jointly optimize the accumulator mux, base lane, and HardFloat Pre. Mul/Post/Round stage boundaries remain explicit. No RTL, cycle, context, generated-file, array, frequency, or interface change is approved. Retiming and timing exceptions are forbidden.

Formal approval and source pins:

```text
reports/L5_2_REVISION7_APPROVAL.md
config/l5_revision7_policy.json
```

L5.2 closes only after single context-lane WNS >= 0 with zero unmapped/unresolved, mapped equivalence, real 512-lane E1 rerun, and structural H3 with 512 lane instances and WNS >= 0.

## Parallel sandbox closure

Blocked Attention cycle E0 covers q128/q384/q1024 with the accepted 16x32 Matrix geometry, four-context feedback, 16-query/32-key tiles, GQA 6:1 reuse, and Block128 M/L/O merges.

```text
q128 serialized cycles   65,284
q384 serialized cycles   656,644
q1024 serialized cycles  4,823,044
q1024 summary merges     43,008
score/probability DDR    0 bytes
```

This is cycle-structured E0, not real stream E1/E2 or integrated E3.

## Global order

```text
L5.2 Revision-7 lane E4/equivalence/H3
→ L5.3 Blocked Attention E1/E2
→ L5.4 fused SiLU DSE
→ L5.5 queue/DMA/DDR E3
→ L5.6 28-layer q1024 >=300 token/s
→ L6 quantized paths
→ L7 production Sequence Memory
→ L8 Qwen3.5/Qwen3.8 backends
→ L9 llama.cpp
→ L10/L11 physical closure and DSE
```
