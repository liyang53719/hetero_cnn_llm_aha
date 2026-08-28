# L5.2 Revision 8 review request

## Revision 7 outcome

Revision 7 passed three reviewed gates:

- source-remap single lane: WNS `+0.000141501 ns`, zero unmapped/unresolved;
- approved post-synthesis gate comparison: 120,032 cycle-exact RTL/gate
  comparisons, zero mismatch and zero unknown output;
- real 512-lane/four-context E1: 1,000,000 dependent steps at II=1 and 10,000
  random-backpressure steps pass.

Structural H3 fails at WNS `-0.926028 ns`, TNS `-49161.85 ns`, with zero
unmapped/unresolved references, 512 instances of one accepted lane, and area
`1379700.051722` library units.

## Root cause

All top critical paths start at scheduler `fifo_count_q`, traverse
completion/`issue_bypass` generation and the 512-way context broadcast, then
enter the accepted lane's accumulator mux and HardFloat Pre logic. Arrival is
1.80 ns against 0.87 ns required. The accepted lane alone assumes bypass is
available at the 0.10 ns input budget; full H3 delivers it at approximately
0.99 ns. Mul/Post/Round and lane mapping are not the blocker.

## Requested Revision 8 scope

Recommended decision: authorize a control-only RTL change that prepares the
same-cycle bypass select before the FMA output cycle and localizes the final
select at each lane. The design may carry completion context/valid metadata
alongside the existing four-stage pipeline or derive a one-cycle-early FIFO
head prediction, but must preserve:

- exactly four architectural accumulator contexts;
- four-cycle data feedback latency and no-stall II=1;
- all public ports, numerical operations and generated HardFloat RTL;
- exact stall, completion, tag, last and error behavior;
- 16x32/512 physical lanes and 1.0 ns target.

The review should freeze one specific implementation before coding. A fifth
context/cycle, lower frequency, false/multicycle path, generated-file edit, or
omitting the FIFO invariant is not acceptable.

## Required gates if approved

1. scheduler/bypass assertions and 100,000-operation recurrence stress;
2. real 1,000,000-step/10,000-backpressure E1;
3. source-to-mapped equivalence for every changed component;
4. component timing for scheduler/broadcast/lane;
5. structural H3 WNS >= 0 with zero unmapped/unresolved;
6. area delta and all source/netlist/report hashes;
7. no claim beyond component-level DC; L10/post-route signoff remains open.

If no control RTL change is approved, L5.2 must remain FAIL at the frozen 1 GHz
gate; additional synthesis-only retries are not justified by the measured
1.80 ns path.
