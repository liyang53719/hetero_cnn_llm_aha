# L5.5 balanced 8x8 Attention SFU sandbox preflight

## Accepted local boundary

The measured 4-lane tile / 4-row merge candidate is numerically and physically valid, but its q1024 projection is not acceptable as an L5.5 entry point:

```text
nominal 315.488706 t/s
stress  314.448097 t/s
review floor 315 t/s
```

The component result is retained as E1/E4 evidence, while L5.5 remains open.

## Measured-calibrated decomposition

For the accepted 4-lane tile:

```text
512 exponent weights / 4 lanes = 128 work cycles
496 reduction adds / 4 lanes   = 124 work cycles
measured nominal               = 357 cycles
measured stress                = 372 cycles
calibrated fixed/elastic cost  = 105 / 120 cycles
```

For the merge path, four rows share one 289-cycle nominal / 307-cycle stress transaction. q1024 requires 43,008 merge rows.

## Recommended candidate

Use the same 16x32 tile storage and FP32 order, but instantiate:

```text
8 elastic tile math lanes
8 parallel M/L/O merge rows
```

The conservative model adds 8 cycles for the extra tile-lane fanout and 16 cycles for the wider merge group. It predicts:

```text
tile stress cycles       254
merge8 stress cycles     323
q1024 SFU stress cycles  4,955,136
stress projection        322.944106 t/s
margin over 315          2.522%
margin over 320          0.920%
```

The conservative linear area upper bound is 684,314 library units. Actual area should be lower if control/store resources are shared.

4x8 and 8x4 candidates clear 315 t/s, but do not clear the preferred 320-t/s engineering floor under the same conservative model. 8x8 is therefore the minimum balanced candidate with explicit margin.

## Local hard gates

1. Eight-lane tile and eight-row merge must use the same FP32 operation order and on-chip weight path.
2. Numerical mismatch must be zero against the frozen vectors.
3. Nominal and deterministic random-backpressure E1 must pass with no loss, duplicate, reorder, deadlock or lane divergence.
4. CLN22UL 1.0 ns WNS must be nonnegative; unmapped and unresolved must be zero.
5. Measured stress projection must be at least 315 t/s. The preferred engineering gate is 320 t/s.
6. Score and probability DDR traffic must remain zero.
7. Only after these gates pass may the design enter real Matrix/SFU/iDMA/DDR E3.

The source-ready `fp32_mlo_merge8_candidate.sv` is provided. The eight-lane tile still requires local RTL integration because the existing tile store has a four-write-port interface.
