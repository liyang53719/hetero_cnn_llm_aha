# Canonical architecture and execution plan v6.4

## Accepted state

- L5.1 Block128 E1/component E4 accepted. WNS is `+0.0000136495 ns`; the component has effectively zero engineering margin and is not post-route signoff.
- L5.2 real 16x32/512-lane, four-context E1 accepted: 1,000,000 dependent issues at II=1 and 10,000 random-backpressure operations.
- Revision-7 source-remapped lane passes marginally at `+0.000141501 ns`.
- Revision-7 mapped functional comparison passes 120,032 cycles with zero mismatch/unknown.
- Revision-7 structural H3 fails: WNS `-0.926028 ns`, TNS `-49161.85 ns`, zero unmapped/unresolved.

## Current critical path

Revision-7 H3 exposes a true cross-hierarchy path:

```text
scheduler FIFO/completion state
→ same-cycle completion/bypass decision
→ global context-control fanout
→ lane accumulator select
→ HardFloat Pre
→ pre_c register
```

The lane itself passes only when its inputs arrive under the local block budget.
The global completion path consumes roughly another cycle before reaching that
lane. No further Revision-7 synthesis-boundary retry is authorized.

## Revision 8A candidate

Revision 8A is approved as candidate source only. The four lane-local context
banks become the output-stage registers. Post-to-Output advancement writes the
rounded result into the aligned context bank; external completion/busy/valid
state remains tied to the original output handshake. The next same-context
issue reads the already-written local bank, removing completion/broadcast from
the FMA data path.

```text
front control: scheduler + elastic valid chain + context tags
32 × cluster16: 512 physical lanes, four banks/lane
retained reset/flag glue
```

Frozen invariants:

```text
16x32 physical array
4 contexts
4-cycle feedback
1 GHz
unchanged public ports
unchanged generated HardFloat
no retiming or timing exceptions
```

Sandbox evidence is E0/source-ready only: 1,000,000-operation public-cycle
differential, 500,000 additional multiseed operations, source/Tcl contracts,
and local execution scripts all pass.

L5.2 closes only after:

```text
Revision7-vs-Revision8A source compare
candidate 512-lane E1
candidate arbitrary-context E1
lane mapped equivalence
lane, cluster16, front-control and structural H3 WNS >= 0
unmapped/unresolved = 0
area/power recorded
post-mapping E1 rerun
```

## Revision 8B-A approved physical distribution

Revision 8A failed structural H3 after all component/E1/equivalence gates
passed. Revision 8B-A is therefore approved as a cycle-neutral combinational
fanout tree: one front output feeds a 1-to-4 level, then four 1-to-8 levels feed
the 32 cluster-local leaves. It retains 4-stage/4-context/four-cycle feedback,
16x32/512 lanes, 1 GHz, public command behavior and generated HardFloat.

The tree is a mapped physical boundary, not a hierarchy of unproven `assign`
statements. H3 must have zero max-transition/max-capacitance violations and
zero unresolved/unmapped cells. Front and cluster boundaries remain retained;
only broadcast/top glue may be compiled. All violating control/context and A/B
operand-distribution roots found by H3 must be covered.

Do not add an FMA stage during Revision 8B-A. After one normal and one
high-effort attempt, if transition/capacitance violations are both zero and H3
still has negative 1 GHz WNS on a non-fanout-dominated path, Revision 8B-B is
authorized: stop tuning 4/4 and switch to 5-stage/5-context with a 3-bit
internal context tag. The public 128-bit command remains unchanged, and all
scheduler/tag/bank/equivalence/E1/H3 gates must be rerun.

Binding policy: `config/l5_revision8b_a_policy.json`.
Approval: `reports/L5_2_REVISION8B_A_APPROVAL.md`.

### Revision 8B-A measured outcome and 8B-B activation

Revision 8B-A passed all functional/mapped-distribution gates and eliminated
H3 DRC: broadcast WNS `+0.302272 ns`, operand-distribution WNS `+0.379584 ns`,
H3 max-transition/max-capacitance/unmapped/unresolved all zero. Structural H3
still has WNS `-1.3073 ns`. The remaining 2.08 ns path crosses the mapped
distribution and HardFloat Pre before `pre_meta_q`; it is not an unfixed DRC.

The frozen fallback has therefore triggered. Revision 8B-B is active: add one
cluster-local registered input/Pre boundary, move to a 5-stage pipeline and
five physical contexts with 3-bit internal tags. No more 4/4 tuning is allowed.
The public 128-bit command and generated HardFloat remain unchanged.

Activation: `reports/L5_2_REVISION8B_B_ACTIVATION.md`.

## Parallel sandbox closure

Blocked Attention cycle E0 remains:

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
L5.1 PASS
├→ L5.2 Revision 8B-A/B physical closure
├→ L5.3 Blocked Attention E1/E2
└→ L5.4 fused SiLU E1/E4
{L5.2,L5.3,L5.4} PASS
→ L5.5 queue/DMA/DDR E3
→ L5.6 28-layer q1024 >=300 token/s
→ L6 quantized paths
→ L7 production Sequence Memory
→ L8 Qwen3.5/Qwen3.8 backends
→ L9 llama.cpp
→ L10/L11 physical closure and DSE
```

L5.3 may use the frozen Matrix transaction contract and Revision 8A functional
baseline without claiming canonical Matrix integration. L5.4 is independent.
L5.5 is the mandatory convergence point and may not close until all three
parallel branches pass.
