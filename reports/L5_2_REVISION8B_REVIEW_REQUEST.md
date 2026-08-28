# L5.2 Revision 8B architecture review request

Resolution: **APPROVED AS REVISION 8B-A**. The binding decision and fallback
rules are in `reports/L5_2_REVISION8B_A_APPROVAL.md` and
`config/l5_revision8b_a_policy.json`.

## Decision requested

Revision 8A passes source/cycle comparison, real 512-lane E1, adversarial E1,
lane mapping, mapped lane equivalence, cluster16 mapping and front-control
mapping. It fails the frozen structural-H3 timing/DRC gate and therefore is not
promoted to canonical RTL.

Measured H3 evidence at 1.0 ns:

```text
hierarchy          1 front + 32 cluster16 + 512 physical lanes + 1 glue
WNS                -10537.7 ns
unmapped           0
unresolved         0
max-transition     53455
max-capacitance    10
cell area          1353676.511670
```

The first failing path is scheduler/front control through the retained
top-level scalar broadcast into 32 clusters and 512 lanes. The front and
cluster components close separately, but H3 retains their mapped boundaries
without a mapped fanout distribution tree.

## Recommended Revision 8B boundary

Add a source-level, cycle-neutral `front_to_cluster_broadcast32` block between
the single front control and the 32 cluster16 instances. It must replicate the
stage enables, context tags and control fields into 32 cluster-local registered
or buffered outputs while preserving all public cycle behavior and the frozen
four-cycle same-context feedback contract.

Target hierarchy:

```text
1 front-control
1 broadcast32 fanout distribution block
32 cluster16
1 retained flag/reset glue
```

The broadcast block must be mapped and included in equivalence and H3 timing;
it is not permission to add an architectural context, alter the public
completion point, reduce the 16x32 array, lower frequency, or change generated
HardFloat RTL.

## Frozen prohibitions

- no wire-load-model manipulation or transition suppression;
- no false-path or multicycle exception on synchronous data/control;
- no flat 512-lane compile and no silent top-level optimization;
- no generated HardFloat edits;
- no fifth context or fifth feedback cycle;
- no candidate promotion before every gate passes.

## Required Revision 8B gates

1. Revision8A-vs-Revision8B source RTL compare for at least 120,000 cycles.
2. Broadcast32 component DC: WNS >= 0, zero transition/capacitance violations.
3. Broadcast32 mapped gate comparison with zero mismatch/unknown.
4. Structural H3: exactly 1 front, 1 broadcast32, 32 clusters, 512 lanes;
   WNS >= 0, zero unmapped/unresolved and zero transition/capacitance violation.
5. Post-map 1,000,000 dependent-step E1 plus 50,000 adversarial operations.
6. Report area and power deltas against Revision 8A; do not claim post-route
   signoff from component-level DC.

Revision 8B-A implementation is authorized. Revision 8A remains non-canonical.
L5.3/L5.4 component development is parallelized, but L5.5 integrated E3 still
waits for L5.2, L5.3 and L5.4 to pass.
