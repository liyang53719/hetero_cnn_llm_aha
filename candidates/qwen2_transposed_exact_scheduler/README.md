# Transposed exact-tree: bounded cold ingress baseline

Source-only integer/event candidate. This directory does not execute tensor
arithmetic, Chisel, RTL, a full block or CI. The graph and canonical protocol
are imported unchanged from `qwen2_exact_tree_scheduler/model.py`, pinned by
SHA256 in the tests. Its prior arithmetic evidence is not a new numeric run.
Base commit: `6576194c5dc8e050c281dcca8f19c404250741fe`.

Run:

```
python -m pytest -q candidates/qwen2_transposed_exact_scheduler/test_model.py
python -m candidates.qwen2_transposed_exact_scheduler.model
```

## Real layout and identities

Logical X[M128,K1536] lives in the existing A SRAM (688 KiB). Its BF16 storage
is 384 KiB. Public21 Norm writes FP32 containers to DDR and Dense is configured
`activation_bf16=false`: actual cold ingress reads **768 KiB**, not 384 KiB.
Every ordinary Q/K job clears and reloads A; only N windows within a job reuse it.
Norm's complete output ACK/publication precedes Dense. Whole-block RMS-to-A
residency is BLOCKED/unproven and its cycle field is null.

X[m,k]: bank=(k&15) XOR (m//16), word=(k//16)*8+m//16, lane=m%16.
Its words occupy rows0..767. Each issue reads eight A banks for X128.
Logical W[k,N32] occupies the existing B SRAM (80 KiB); one issue reads two
banks for W32. Unique W per panel is 96 KiB, streamed through finite slots.
One partial needs 24×64B=1536B; the current serialized baseline alternates two
existing 40-KiB halves, each with only a 1.5-KiB payload. This does NOT support
five simultaneously supplied partial chains. A future five-chain mode needs
at least five distinct partial identities/slots (7.5 KiB), still within B.

The physical FMA A port receives W0..15; its B envelope holds X0..127 plus
W16..31 in elements128..143. Slices0..3 use low W; slices4..7 use high W and
broadcast the same X128 wires. Logical Y[m,n] maps to physical
row=n%16, column=(n//16)*128+m. No additional X SRAM copy is credited.

Supply tags bind epoch/tile, Q-or-K, width, nbase, relative tensor address,
B half and t, real X k=64*t+p, plus the original canonical node/context fields.
Panels0..47 are Q(width1536);48..55 are K(width256). Only the exact next panel is
accepted. Default Q→K invalidates A ready in the engine itself. Explicit
`shared_qk_lease=True` selects an unimplemented cross-job lease; no existing
owner behavior is claimed. ACKs must match these complete identities.

New B indexing separates true X k from B-slot t and accumulator context. The
old read.k drives both X and B, so the revised route is explicitly NEW. Ordinary
five transposed contexts represent five different N32 output tiles, whereas
this candidate uses five partials of one tile. That also requires a new mode.

## Executable ingress choices

`legacy_rmw` follows real FP32-container transport:768 row clears,12288 external
64B reads, conversion to one32B BF16 segment each,12288 full-bank RMW commits.
An RMW reads512B and writes512B while accepting only32B of new useful payload.
It cannot run beside operand reads through the current gate. The modeled ACK
is a control receipt; it does not imply a new512B response-hold register.

`gather2_candidate` is a NEW bounded write-combining route:
- Exactly two512B BF16 buffers,1KiB total
- A block takes16 non-contiguous FP32 64B row segments,1024B wire data
- Segment offset=((16*group+row)*1536+16*kword)*4; row stride6144B
- Converted block commits all16 bank words at word=8*kword+group
- Destination bank=k_lane XOR group, lane=row
- Every row identity and valid bit is checked; all16 successful segments and
  matching bulk-write ACK are required before releasing the buffer
- Exactly768 bulk commits; no A clear or RMW is needed in this new route
- One DMA segment and one bulk commit can be outstanding, bounded by two
  buffers. Abort drains accepted operations but cannot publish resident A

It still reads768KiB and still uses the old single-beat DMA in this batch.
The sixteen row addresses are NOT a contiguous1024B burst. No strided DMA
bandwidth has been silently granted. The event baseline is deliberately
serialized; tests separately exercise both buffers while a bulk ACK is held.

## Exact tree, resources and limits

The same S04/S26/S15/S37 graph, five accumulator contexts totaling 80 KiB and three
16-KiB spill/read pairs remain. FP32 Add, context packet access/restore and
compact A-slot commit interfaces are UNIMPLEMENTED. Existing80-KiB leaf result
registers,32-KiB result FIFO and16-KiB finalValue remain separate and untouched.
No result storage is borrowed by this candidate.

Two compact16-KiB slots reserve A rows768..831, giving416KiB total with X. This
is a NEW direct-bank route. Existing TileBank's two logical16-KiB slots have a
fixed160-KiB address reservation, giving544KiB total; its transactions read all
16 banks, writes RMW, and its quiescent gate does not permit compute overlap.
Existing seed/restore control also requires full arithmetic quiescence; it is
not an arbitrary tree-context restore API.

One active DMA transfer, existing1KiB mailbox (modeled peak64B), and four
operand credits (serial model peak1). All arithmetic feedback is at least five
stages; every return and local/output ACK is charged. No unbounded payload
queue, fake zero-multiply hold, or freely reusable context exists.

Default serial one-panel results, first cold read/clear through final raw ACK:
- Legacy RMW:92,288 model cycles
- New A gather, same old DMA/whole-context tree:67,712 model cycles

These are model policy costs, not hardware cycles or optimized throughput.
The model retains the original ordered FP32 graph and has no payload-carrying
FMA cosimulation. `hardware_cycles` and `hardware_utilization` are null.

## Explicit NO_GO bounds and the next required changes

For56 Q/K panels, pure issue arithmetic is89,600 cycles and its ceiling96%.
That excludes supply and is not the complete performance bound.

- Existing W DMA is one-beat/single-active, with no request accepted on its
  response edge: at least172,032 Q/K W cycles, ceiling50%, even with free X
- Exact partial t steps have DDR stride64*N*2 (Q:196608B), not adjacent beats;
  a double partial buffer cannot fix long-run DMA throughput
- Whole-vector locks give context occupancy10619 context-cycles per tile,
  hence at leastceil(10619/5)=2124 cycles, ceiling72.3164%, even with free data
- Cold X clear+RMW resource floor is25,344 cycles; real FP32 owner state gating
  strengthens this to at least37,632 before additional aFence/setup/backend cost
- Even hypothetical one-load Q/K sharing plus arithmetic alone is114,944 cycles,
  ceiling74.833%. Existing Q/K has two cold jobs. Stronger combined bounds are
  emitted separately; no cold initialization is omitted

Reaching an80% architectural target therefore needs all of: bounded tagged
strided/gather descriptors or fully charged prepacking, explicit A-ingress
improvement, and changed whole-context locking/frontier ownership. The first
must preserve total512-bit bandwidth and distinguish one external descriptor,
beat credits and the backend's four internal AXI transactions. The latter must
use a default-off mode with old result readers isolated and preserved. None
of those absent interfaces is claimed implemented here. Separate follow-on
candidates must prove them; no claim of achieving80% is made by this batch.

## Read-only source anchors

- `transposed_owner/TransposedDenseBanks.scala:37-38,43-74,82-114`: SRAM,
  X scatter/gather, B half formula and ports
- `transposed_owner/TransposedDenseOwner.scala:61-66,99-119,233-282`: real DMA,
  wire routing, single-beat admission and A ingress fence
- `transposed_route/combined_service.patch:114-130`: physical slice routing
- `official_bf16/execution.py:61-64`, `official_bf16/owners.py:24-59`: FP32-wire
  Norm→Dense boundary, under `candidates/qwen2_resident_matrix/`
- `ffn_tiles/model.py:69-72,150-245`: existing TileBank layout/gates/RMW
- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/IdmaWeightBurst.scala:17-29,72-103,130-153`:
  finite mailbox, single descriptor, internal segments, validated LAST
