# Local-agent handoff v6.3

State: L5.2 Revision 8A component/E1/equivalence gates PASS; structural H3
FAIL_TIMING_DRC. Frozen stop rule applied. Wait for Revision 8B architecture
review; do not rerun H3 or promote candidate RTL.

## Revision 8A passed evidence

- Contract: primary 100,000 and multi-seed 500,000 operations PASS.
- Revision7-vs-Revision8A RTL compare: 120,000 cycles PASS.
- Real 16x32/512-lane E1: 1,000,000 dependent steps at II=1 plus 10,000
  random-backpressure steps PASS.
- Adversarial E1: 50,000 operations PASS.
- Lane DC: WNS `+0.000101686 ns`, area `2608.970004`, zero
  unmapped/unresolved.
- Mapped lane compare: 120,032 cycles, zero mismatch/unknown.
- Cluster16 DC: WNS `+0.0000194907 ns`, 16 lane instances, area
  `42268.863177`.
- Front-control DC: WNS `+0.000527799 ns`, area `381.107998`.

## Frozen blocker

Structural H3 contains exactly one front, 32 cluster16 instances, 512 physical
lanes and one glue instance, with zero unmapped/unresolved, but fails:

```text
WNS                 -10537.7 ns
max-transition      53455
max-capacitance     10
cell area           1353676.511670
```

The first path is scheduler/front control through top-level scalar fanout into
32 retained clusters/512 lanes. Separate front and cluster mappings see small
boundary loads; the retained H3 hierarchy has no mapped fanout distribution
tree. This is an architecture-boundary failure, not permission to change wire
loads, add exceptions, flatten 512 lanes, retime, lower frequency, or add a
context/cycle.

## Next action

Review [L5_2_REVISION8B_REVIEW_REQUEST.md](../L5_2_REVISION8B_REVIEW_REQUEST.md).
The recommendation is one cycle-neutral source-level
`front_to_cluster_broadcast32` block, included in mapped equivalence and H3
timing/DRC. No implementation starts before review.

Canonical evidence:

- `reports/execution/l5_revision8a_local_result.json`
- `reports/execution/l5_revision8a_gate_compare_result.json`
- `config/l5_revision8a_policy.json`

Candidate RTL under `rtl/matrix/candidates/rev8/` was not edited or promoted.
The two user runtime setup scripts remain untracked and untouched.
