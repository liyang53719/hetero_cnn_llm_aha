# Local-agent handoff v6.4

State: Revision 8B-B 5-stage/5-context functional E1 PASS; component E4 next.

## Frozen reason

Revision 8B-A H3: transition/cap/unmapped/unresolved `0/0/0/0`, WNS
`-1.3073 ns`; therefore no return to 4/4.

## Revision 8B-B implemented

- Cluster-local registered A/B/context/clear input boundary before HardFloat Pre.
- Five-stage elastic control and tag pipeline.
- Five accumulator contexts, 3-bit internal tags.
- 16x32/512 lanes, 1 GHz target.
- Public 128-bit command and generated HardFloat unchanged.

## Passing evidence

```text
source contract                         PASS
1M dependent, five contexts             II=1, window 1,000,000 PASS
10k random backpressure                 PASS
50k arbitrary legal contexts            PASS
8B-A vs 8B-B full 512-lane compare      120,000 PASS
required latency shift                  exactly +1 cycle
```

## Unique next action

Map `bf16_context_fma_pipeline_lane5_rev8b_b_candidate` at 1.0 ns, then run
mapped equivalence. Continue cluster16/front5/broadcast15/H3 only after lane
passes. CPU 8-23, 24/30G, 600 s per attempt.

L5.3/L5.4 remain parallel; L5.5 remains the join. Do not modify generated RTL
or the two untracked user runtime scripts.
