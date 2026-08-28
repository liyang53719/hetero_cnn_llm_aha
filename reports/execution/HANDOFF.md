# Local-agent handoff v6.2

State: Revision 7 lane/equivalence/real E1 PASS; structural H3 FAIL_TIMING.
Wait for Revision 8 review before changing scheduler/bypass RTL.

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

## Local Revision-7 lane result

- Normal-effort WNS `+0.000141501 ns`; no high-effort retry ran.
- 0 unmapped/unresolved; 5,029 leaf cells; 427 sequential cells.
- Area 2,674.490005, which is 32.6489% below the Revision-6 high-effort lane.
- Formality is absent. Follow
  `reports/L5_2_REVISION7_GATE_COMPARE_PLAN.md`; only a real trace-identical
  post-synthesis comparison may supply `REV7_EQUIVALENCE_EVIDENCE`.

## Revision-7 final outcome

- Approved post-synthesis comparison PASS: 120,032 cycle-exact RTL/gate
  samples, 0 mismatch and 0 unknown output.
- Post-equivalence real E1 PASS: 1,000,000 dependent steps and 10,000 random
  backpressure steps on 512 lanes/four contexts.
- Structural H3: WNS `-0.926028 ns`, TNS `-49161.85 ns`, area
  `1379700.051722`, 0 unmapped/unresolved, 512 instances/one lane variant.
- Critical path: scheduler `fifo_count_q` through completion/bypass generation,
  context broadcast and lane mux/HardFloat Pre; arrival 1.80 ns.

Do not retry Revision 7. Review
`reports/L5_2_REVISION8_REVIEW_REQUEST.md`. Recommended scope is an early/local
bypass-select control change with unchanged four-context/four-cycle semantics.

## Parallel progress

Blocked Attention cycle E0 freezes q384 at 656,644 serialized cycles, q1024 at 4,823,044 cycles, 43,008 q1024 summary merges, and zero score/probability DDR materialization. Real stream E1/E2 remains local work.
