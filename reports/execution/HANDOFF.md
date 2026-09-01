# Local-agent handoff v7.25 — main only

## Closed in this checkpoint

```text
v7.8 sandbox baseline                       PASS
L10.1 frozen-DDC owner hierarchy link/STA  PASS
  WNS +0.00000864267 ns; area 2,313,314.648873 um2
  6 owners; parent local area 0; double-count 0
L10.2 SRAM macro DB inventory              PASS
  4096 KiB; 124 physical macros; overlap 0
  SP/DP Liberty->DB and timing arcs linked
Payload P1                                PASS, 168/168 checkpoints
Payload P2 reference continuity           PASS, 7/7 groups bit-exact
Payload P2 RTL transaction control         PASS, 168/168, injection 0
P2 real command-to-payload operator slice  PASS, 1568 BF16 bit-exact
  graph Command128 -> fabric/event -> RMSNorm1536 -> Revision8B-B Matrix
```

## Open boundary

P2 now has one real layer-0 RMSNorm-to-Q-Matrix operator slice, but payload is
still testbench staged. A complete layer, descriptor-backed payload memory,
seven continuous four-layer groups and P3 continuous 28-layer remain OPEN.

Goal resumed after explicit user approval of dtype and SFU_PROGRAM encoding.
Canonical config, software round-trip, 12-case RTL decoder and the formal
6188-record image all PASS. Descriptor-backed payload execution remains open.

L10.3/L10.4 remain OPEN. DP GDS2 and all SRAM LEF are blocked by the ARM
physical-view generator; no post-route/PVT/OCV or SAIF claim is made.

## Next

Pinned llama.cpp `0b5be7e4` now runs q1024 as one 1024-token ubatch; PyTorch
and llama argmax match and Top-10 overlap is 10/10. The 930-node/338-tensor
capture lowers to 588 traceable commands: Matrix 252, SFU 308, KV 28. All pass
production command/event submission under random backpressure. This supersedes
the invalid 252-command nine-phase template that collapsed Q/K/V bindings.
Capture is decode-only; layers 0-26 retain q1024 and layer27 legally narrows to
the final token required by the frozen LM-head contract.

Real Matrix/SFU endpoint RTL now passes the first two graph-derived commands:
2 completions, 1536 RMS outputs, 1536 Matrix steps, 32 Matrix outputs, 1568
BF16 values bit-exact, event ordering and random backpressure PASS. Public
encoding is approved and formal packing is complete:
588 commands, 1764 chains/6188 records, max chain 6, 954 DDR objects, 0 overlap,
28 KV layers, FP32 score tile 2 KiB and BF16 probability tile 1 KiB. Device
shapes are row-major (`[1024,1536]`, Q `[1024,12,128]`), not GGML `ne[]` order.
The parameterized packer passes all 6188 records in explicit test-only mode and
hard-rejects unapproved input; normal approved mode produces hash
`172dfcb799b8...`. Next connect Shared-L2 payload to that image, then extend one
layer and seven groups. Preserve CPU 8-23, 24/30 GiB
caps, <=600 s tasks, main-only pushes, and the two untracked runtime scripts.
