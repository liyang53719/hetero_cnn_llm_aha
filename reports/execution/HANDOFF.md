# Local-agent handoff v7.33 — main only

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
Canonical config, software round-trip, 12-case RTL decoder, compact 164,544-byte
formal image and production descriptor-port fetch all PASS. Descriptor-backed
payload tensor movement remains open.
The two-command RMSNorm-to-Q context now snapshots six roots/shapes from the
formal image, validates q1024 BF16/FP32 and address continuity, and rejects a
bad event dependency before any fetch. Separate RTL gates now add the exact
4-op DMA plan and real Shared-L2 payload: 1680 reads, 49 writes, RMS1536,
Matrix1536 steps/32 outputs and 1568 BF16 bit-exact under random L2 backpressure.
The same path now passes as one RTL top: 12 descriptor fetches → 4 DMA requests
→ Shared-L2 → real engines → 2 completions → writeback. DMA responses are still
modeled in that top. Separately, pinned/clean iDMA VCS passes the exact plan:
4 abstract → 1539 flat requests, 1681 read/write AXI beats, 1536 2D rows and
first/last addresses. The AXI-to-Shared-L2 bridge now also passes actual data:
1680 load beats compare byte-exact in L2 and the 64-byte store compares in DDR.
The unified VCS run now embeds that real DMA chain: formal descriptor fetch,
pinned iDMA, byte-exact L2 staging, real RMSNorm/Matrix, two completions and DDR
writeback all PASS in one simulation. Scope remains token0/Q columns0-31 only.
Vector audit corrected an earlier mapping error: the old random sampled Q rows
were replaced by exact safetensors physical output columns0-31 laid out as
1536 rows × 64 B with 3072 B source stride. All four payload/DMA gates reran PASS.

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
hard-rejects unapproved input; compact approved image hash is `c8bc57cf8690...`.
All 6188 records pass production protocol fetch; real ARM macros sample all four
bank groups/lanes, backed by retained L3 macro 100k. Six-root tile context also
passes 12 descriptor fetches. Monolithic tile top passes; next bind its four
tile path is unified; next extend Q across all 48 column tiles without reloading
weights or completing the command early, then extend one
layer and seven groups. Preserve CPU 8-23, 24/30 GiB
caps, <=600 s tasks, main-only pushes, and the two untracked runtime scripts.
