# L5.2 Revision 8B-A approval

Status: **APPROVED** on 2026-08-28.

This approval resolves the decision requested in
`reports/L5_2_REVISION8B_REVIEW_REQUEST.md`. Revision 8A remains rejected as a
canonical H3 implementation; its passing E1/component/equivalence evidence is
retained as the functional baseline.

## Revision 8B-A

Implement a cycle-neutral combinational fanout distribution boundary:

```text
front control
  -> 1-to-4 distribution
     -> 4 x 1-to-8 distribution
        -> 32 cluster-local leaves
```

Revision 8B-A retains the 4-stage FMA, four contexts, four-cycle feedback,
16x32/512-lane array, 1.0 ns clock, public command behavior and generated
HardFloat. No FMA pipeline stage is added in this phase.

The tree distributes all front-to-cluster control and context fields. Before
RTL freeze, H3 max-transition/max-capacitance roots must be inventoried; any
violating A/B operand-distribution nets must receive the same bounded physical
distribution treatment.

The implementation must map to a real buffer tree. A hierarchy of RTL
`assign` statements without mapped cells and H3 transition/capacitance evidence
does not satisfy this approval. Front and cluster16 remain retained boundaries;
only broadcast/top glue may be compiled. Flat 512-lane compile is forbidden.

## Revision 8B-A acceptance

- Revision8A-vs-Revision8B-A compare >=120,000 cycles.
- 1,000,000 dependent steps at II=1 plus 10,000 random-backpressure steps.
- 50,000 adversarial operations.
- Broadcast mapped comparison: zero mismatch and zero unknown.
- Structural H3: 32 cluster16, 512 lanes, zero unresolved/unmapped.
- H3 max-transition violations = 0 and max-capacitance violations = 0.
- H3 WNS >= 0 at 1.0 ns.
- Record area and power delta; no post-route claim.

One normal and one high-effort attempt are allowed, each bounded to 600 s.

## Authorized Revision 8B-B fallback

Do not add an FMA stage pre-emptively. Revision 8B-B is automatically
authorized only after Revision 8B-A has zero transition/capacitance violations,
zero unresolved/unmapped, has completed its normal and high-effort attempts,
and still has negative 1 GHz WNS on a path not dominated by unfixed fanout DRC.

When that conjunction is true, stop tuning 4/4 and switch formally to:

```text
5-stage FMA
5-context interleave
3-bit internal context tag
unchanged public 128-bit command
```

Revision 8B-B must revalidate scheduler/scoreboard, tags, accumulator banks,
same-context reuse, source/mapped equivalence, one-million-step II=1 and H3.

## Parallel L5 execution

The former strict order `L5.2 -> L5.3 -> L5.4` is removed:

```text
             +-> L5.2 Revision8B-A/B physical closure --+
L5.1 PASS ---+-> L5.3 blocked Attention E1/E2 -----------+-> L5.5 E3
             +-> L5.4 fused SiLU E1/E4 -----------------+
```

L5.3 may use the frozen Matrix transaction contract and Revision8A functional
baseline, but cannot claim canonical Matrix integration. L5.4 may proceed
independently. L5.2, L5.3 and L5.4 must all pass before L5.5 integrated E3;
L5.6 still requires the final canonical Matrix revision.

The machine-readable contract is `config/l5_revision8b_a_policy.json`.
