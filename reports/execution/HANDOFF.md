# Local-agent handoff v6.2

State: `REVISION_7_APPROVED_WITH_GATES` at L5.2.

## Accepted

- L5.1 E1/E4 is accepted under the frozen component gate. Block128 WNS is only `+0.0000136495 ns`, so this is not post-route or variation signoff.
- L5.2 real 16x32/512-lane, four-context E1 is accepted: 1,000,000 dependent steps at II=1 and 10,000 random-backpressure steps pass.
- Structural array, scheduler and broadcast pass component timing.

## Revision-6 blocker

The one context lane remains negative at `-0.034333 ns` normal and `-0.0371628 ns` high effort. The path is `issue_bypass_i` through the local accumulator mux and HardFloat Pre to `pre_c_q`. Mul/Post/Round are not critical.

## Revision-7 approval

Revision 7 may map one context lane directly from the pinned aggregate emitter-generated SystemVerilog plus unchanged base/context lane RTL. DC may optimize across the accumulator mux, base lane and HardFloat Pre. No RTL, cycle, context, frequency, generated file, or public interface change is permitted. Retiming, timing exceptions and a flat 512-lane compile are forbidden.

Run:

```bash
python3 scripts/validate_l5_revision7_contract.py
./scripts/run_l5_matrix_context_revision7.sh lane
./scripts/run_l5_matrix_context_revision7.sh equiv
./scripts/run_l5_matrix_context_revision7.sh e1
./scripts/run_l5_matrix_context_revision7.sh top
./scripts/run_l5_matrix_context_revision7.sh e1
python3 scripts/summarize_l5_revision7.py
```

Use Formality when available. An approved post-synthesis gate comparison may be supplied through `REV7_EQUIVALENCE_EVIDENCE`; otherwise stop as `BLOCKED_EQUIVALENCE_TOOL`.

L5.2 closes only when lane WNS, equivalence, the real E1 rerun, and structural H3 WNS all pass with zero unmapped/unresolved references. A lane WNS below `+0.02 ns` is marginal and may proceed to H3 but is not signoff.

## Parallel progress

Blocked Attention cycle E0 freezes q384 at 656,644 serialized cycles, q1024 at 4,823,044 cycles, 43,008 q1024 summary merges, and zero score/probability DDR materialization. Real stream E1/E2 remains local work.
