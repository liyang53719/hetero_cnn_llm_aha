# Local-agent handoff v6.7

State: **L5.2 is closed** at the frozen CLN22UL component/H3 gate. L5.3 is the
primary branch and L5.4 runs in parallel. No newer local-agent evidence was
present when v6.7 was prepared.

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
H3 WNS                           +0.00490451 ns
H3 transition/cap/unmapped/unres 0/0/0/0
Post-map E1                      PASS
```

The boundary is closed only at component/H3 DC. Its timing margin is extremely
small, so post-route/PVT/variation closure remains L10 work.

## Unique local action: L5.3

Implement real streaming `QK -> Block128 M/L/O -> PV` using:

```text
Q tile 16, K/V tile 32, block 128, GQA 6:1
Score FIFO 2 entries, Probability FIFO 2 entries
FP32 M/L/O
Revision8B-B Matrix transaction boundary
zero score/probability DDR materialization
```

Use the numerical and stream E0 reports as Golden/service references. Required
E1/E2: q128, q384, reviewed q1024 rows, 43,008 q1024 merges, random
backpressure, no loss/reorder/deadlock and measured cycles.

## Parallel local action: L5.4

Implement the 128-entry FP16 direct-SiLU LUT with fused `SiLU(gate)*up`. Compare
one-lane and two-lane II=1 implementations. Select one lane when measured
Matrix-producer stall is <=2%; otherwise select two lanes. Run numerical E1 and
1 GHz DC/PPA.

## New sandbox contracts

- GGML: pinned Q8_0/Q6_K/Q3_K/FP16 byte-layout, dequant and shared-dot E0.
  Local gate: build pinned llama.cpp and compare >=10,000 blocks/format.
- Sequence state: ten state domains, partial speculative commit, page COW,
  refcount, epoch/generation and stale-response suppression E0.
- Graph partition: deterministic longest-match segmentation with explicit CPU
  fallback and no model-name conditionals.
- L5.5: discrete-event preflight estimates q1024 at 338.25 token/s for the
  100 GB/s, 16-bank candidate. This is not E3; measured L5.3/L5.4 service
  curves and real iDMA/DDR counters must replace all analytical durations.

L5.5 remains the mandatory join after L5.3 and L5.4.
