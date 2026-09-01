# Local-agent handoff v7.62 — main only

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
The production controller now executes all 48 physical Q column tiles for
token0 in one command: descriptor/RMS/Matrix completion each occur once, 1536 Q
outputs are bit-exact and contiguous in DDR. It uses two alternating 96 KiB
weight buffers; DMA/Matrix overlap is not yet enabled.
True ping-pong is now measured: 816,115 serialized cycles → 450,911 cycles,
ratio 0.5525; DMA and payload overlap for 365,859 cycles with identical 1536 Q
outputs and traffic. Token0 does not prove q1024 Matrix utilization.
Generic projection context derives Q/K/V geometry from formal descriptors.
Raw K and V each pass 256 physical columns/8 tiles with pinned iDMA, Shared-L2,
Revision8B-B, 256 BF16 bit-exact and 54,515 overlap cycles. Bias/RoPE remain open.
Real HardFloat bias add now passes Q/K/V 2048 values after the Matrix BF16
boundary. Real fp32_rope_pair passes token0 Q/K split-half 896 pairs/1792 values.
Projection, bias and RoPE are not yet one event/data chain.
Raw QKV is now one no-injection VCS chain: DDR input/weights → real RMS →
Shared-L2 norm → the same Matrix instance sequential Q/K/V → DDR outputs.
Four formal commands, 98,370 flat iDMA requests and 3,584 values are bit-exact.
Bias audit now matches formal descriptors: GGUF bias arrives as FP32 dtype7
(two 512-bit beats per 32 values), HardFloat adds it after the Matrix BF16
boundary, and Q/K/V 2048 outputs remain bit-exact.
Descriptor-driven Q/K/V bias and Q/K RoPE are now inserted into the raw QKV
run. One VCS chain executes the first nine formal commands with 62 descriptor
fetches, 98,500 flat iDMA requests, 98,882 AXI beats each way and 7,424 BF16
values bit-exact. Projection DDR outputs feed bias and RoPE directly; no
intermediate reference is injected. RoPE fully traverses its three approved
descriptor chains and loads runtime position from DDR. This closes token0
position0 only; nonzero coefficients and the rest of layer0 remain open.
The next formal `l0.kv_append` context now also parses production schema v3:
13 full-chain fetches cover K, V, `0x32`–`0x35` metadata and the referenced
page-table tensor under random backpressure. All 28 frozen layouts match the
planner: 32 KiB table + 1 MiB DDR data/layer, 64 logical 16-token pages and
16 KiB combined K/V per page. Malformed commands and reserved table flags are
rejected. This is context evidence only; PTE writes and KV payload movement are
still open, and the legacy 512 KiB staging adapter is not production DDR KV.
The v3 context is now composed with a 64-page DDR scheduler in one RTL stage.
It emits one root plus 64 leaf PTE field updates and 128 exact 8 KiB K/V iDMA
requests (1 MiB total) under random descriptor/PTE/DMA backpressure. Every K/V
source and combined-page destination address is checked. PTE fields remain
explicit because flags packing is not frozen; the iDMA requests are not yet
bound in that component gate. A subsequent VCS gate now binds all 128 requests
to clean pinned iDMA and one joined AXI DDR: 16,384 read plus 16,384 write beats
and all 1 MiB across 64 pages compare byte-exact. Its source is a deterministic
synthetic preload, not preceding Matrix/SFU output; PTE DDR writes remain open.
The same production RMS/projection/bias/RoPE sources now accept an internal
32-bit token index; no sequence length selects a different RTL. Projection
token1 dynamically proves hidden `+3072` and output `+token_bytes` addresses.
RMS/bias/RoPE token offsets and 16-position position-beat lane selection compile
and retain the complete token0 first-nine PASS. Nonzero RoPE coefficients and
token1 numerical replay remain open; this is addressing evidence only.
Nonzero RoPE is now real RTL, not an address stub. Q and K each retain 64 FP32
coefficient pairs (fixed 1 KiB total state) and advance with theta=1e6 complex
recurrence through the same `fp32_rope_pair` datapath. One payload instance runs
Q0→Q1→K0→K1: 128 coefficient steps and 3,584 BF16 values are bit-exact under
backpressure, with independent Q/K state. Generated 64 base-step constants are
reproducible and marked do-not-hand-edit. Full token0 first-nine still passes.
Token1 full RMS/Matrix/bias-to-RoPE continuity remains open.
Audit corrected the earlier token label before extension: its vector came from
`hs[0][0,-1]` but was called token0 and rotated at position0. That artifact now
retains component arithmetic/protocol meaning only. Canonical llama.cpp tokens
hash `e4151c...`; real DDR rows0/1 are token IDs48/16948. The same production
RTL and descriptors now execute each row through all first nine commands:
7,424 BF16 bit-exact/token, refined RMS NR2, Revision8B-B Matrix, bias and
position0/1 RoPE, no intermediate injection. Total is14,848 exact values.
The first real batch16 Matrix tile now uses every physical 16×32 row: canonical
rows0..15 × Q columns0..31 execute 1,536 K steps, 786,432 effective MACs,
512 BF16 outputs bit-exact and one completion under L2 backpressure. K-major
activation staging gives one 16-value A vector per step. This component gate
preloads normalized activations; batch16 RMS staging, all Q/K/V tiles and
bias/RoPE integration remain open.
Batch16 RMS is now real and directly connected to Matrix in one VCS run. One
refined RMS unit processes canonical hidden rows0..15, loads weight once, writes
token-major norm, then transposes to 1,536 K-major beats. The Matrix consumes
that produced data without activation reference injection: 24,576 RMS +512 Q
tile values, 25,088 BF16 bit-exact, 1,536 Matrix steps and one completion.
Hidden/weights are still preloaded into Shared-L2; descriptor/iDMA binding and
all Q/K/V column tiles remain open.
The generic descriptor-derived batch16 projection controller now closes every
Q/K/V column tile on the real Revision8B-B array. Q uses48 tiles/73,728 steps;
K and V each use8/12,288. Totals:64 tiles,128 abstract DMA requests,98,304
Matrix steps,50,331,648 effective MACs,32,768 BF16 exact and three formal
command completions. These three component runs preload the passing K-major
activation and model DMA; RMS same-run and pinned-iDMA binding remain open.
RMS→Q→K→V now executes as one canonical batch16 VCS chain. Hidden rows0..15
flow through refined RMS/K-major staging and one reusable descriptor-derived
projection controller invoked for formal Q/K/V commands. Result:57,344 BF16
exact,18 descriptor fetches,128 modeled DMA requests,98,304 Matrix steps,
50,331,648 effective MACs and three completions. Activation and intermediate
reference injection are both zero. Hidden/weights and DMA remain modeled;
batch16 bias/RoPE and pinned-iDMA binding are next.
Generic batch16 bias and RoPE controllers now pass all required commands. Bias
Q/K/V produces32,768 exact values using one FP32-bias load per command. RoPE
Q/K runs positions0..15 sequentially with independent state,1,920 total
coefficient steps and28,672 exact values. Each formal command fetches context
once and completes once. Component inputs are canonical preloads; same-run
connection to produced QKV and pinned-iDMA remain open.
The complete canonical batch16 first-nine sequence now passes in one production
controller/VCS run:9 formal commands/completions,62 descriptor fetches,145 DMA
requests, positions0..15,98,304 Matrix steps/50,331,648 MACs,1,920 RoPE steps
and118,784 BF16 exact. RMS→Q→bias→RoPE→K→bias→RoPE→V→bias uses direct produced
tensors with zero intermediate reference injection. The modeled-DMA result is
superseded by the pinned-iDMA result below; q1024 and remaining layer0 are open.
Pinned-iDMA batch16 first-nine now PASS. Directional chunking uses max1024 B for
DDR→local and64 B for local→DDR; dedicated gate has no AXI assertions. Full run
binds clean upstream iDMA, AXI bridge and real Shared-L2 fabric:101,432 flat
requests,104,162 read/write beats,9 completions and118,784 BF16 exact with zero
intermediate injection. Descriptor words still use the formal-image responder;
same-fabric descriptor storage remains a later composition detail.
q1024 P3 backend-equivalent numerical now runs embedding→28 layers→final norm→
full151,936-vocab LM head with588 commands/seven groups and zero hidden
injection. tile32/PV-hilo/balanced-block128/ext32 exp2 keeps all layer errors
≤0.0007788,no score matrix; layer27 SHA=`3268b56c...`. Argmax7559 and Top-10
10/10 match PyTorch. ext32 E1 passes q128 full,block32 and132 merge cases;
1GHz DC passes WNS+0.000000954 ns,area39,600.106,unmapped0 after an index
pipeline repair. Margin is critical sub-1ps. A new2/3/4/8-summary balanced RTL
scheduler passes17 inputs/13 merges and random backpressure bit-exact. Its
4,160-byte register storage makes flat and bottom-up DC hit600s; PPA stays
OPEN_STORAGE_MAPPING. Layer5 q848/head2 now feeds7 exact-model block summaries
to RTL:6 balanced merges/32 beats bit-exact with16 stalls. QK/SFU/PV summary
production is still hardware-semantics,not this RTL run. One in-process C ABI
call now submits588 commands and receives28 ordered completions with zero stage
subprocesses; final SHA matches P3. A pinned-ABI `HETERO` GGML registry/device/
graph_compute shim now writes1,572,864 values with CPU fallback0. It accepts one
custom submission node,not the original930-node graph,and still uses exported
safetensors inputs,so native GGUF/device graph gates stay OPEN.
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
passes 12 descriptor fetches. Monolithic tile top passes. Raw QKV, FP32 bias
and split-half Q/K RoPE now execute as one nine-command no-injection data chain.
KV v3/pinned-iDMA,P3 backend,layer5 balanced RTL and in-process submission pass.
Next partition the original llama graph and bind native GGUF buffers; summary
macro and real layer5 QK/PV remain parallel OPEN. Full all-row RTL remains OPEN.
Preserve CPU 8-23,24/30 GiB
caps, <=600 s tasks, main-only pushes, and the two untracked runtime scripts.
