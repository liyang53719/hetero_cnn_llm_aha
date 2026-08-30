# Local-agent handoff v6.6

State: **L5.2 is closed** at the frozen CLN22UL component/H3 gate. L5.3 is the
primary branch and L5.4 runs in parallel.

## Accepted Matrix boundary

```text
Revision                         8B-B
Physical array                   16x32 / 512 BF16 MAC lanes
FMA stages / contexts            5 / 5
Internal context tag             3 bit
Completion FIFO                  depth 5
1M dependent issue window        1,000,000 cycles, II=1
10k random / 50k adversarial     PASS / PASS
Mapped lane comparison           120,032 cycles, mismatch/unknown 0/0
H3 WNS                            +0.00490451 ns
H3 transition/cap/unmapped/unres 0/0/0/0
Post-map E1                       PASS
```

The above closes L5.2 only at component/H3 DC. Lane, cluster, front and H3
margins remain extremely small, so post-route/PVT/variation closure stays open
in L10.

## Unique next action: L5.3

Implement real streaming `QK -> Block128 M/L/O -> PV` with:

```text
Q tile 16, K/V tile 32, block 128, GQA 6:1
Score FIFO 2 entries, Probability FIFO 2 entries
FP32 M/L/O
Revision8B-B Matrix transaction boundary
zero score/probability DDR materialization
```

Use `reports/execution/l5_blocked_attention_numeric_e0_result.json` as the
numerical Golden and `l5_blocked_attention_stream_e0_result.json` as the service
reference. Required E1/E2: q128, q384, reviewed q1024 rows, 43,008 q1024 merges,
random backpressure, no loss/reorder/deadlock and measured cycles.

## Parallel L5.4

Implement 128-entry FP16 direct-SiLU LUT with linear interpolation and fused
`SiLU(gate)*up`. Build 1-lane and 2-lane II=1 candidates. Select one lane when
Matrix-producer stall is <=2%, otherwise two lanes. Run numerical E1 and 1 GHz
DC/PPA. L5.5 remains the join.

## Additional source-ready contracts

- Sequence Memory: 8 MSHRs, first RTL point 16 outstanding data requests,
  in-order retire, same-page miss coalescing, stale-generation suppression.
- Qwen3.8: deterministic per-layer policy -> Command128 lowering is available;
  bind it to the real GGML graph only after official graph/runtime setup.
