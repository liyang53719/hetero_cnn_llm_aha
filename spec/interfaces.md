# Frozen v0 interface contract

All block-to-block data movement uses ready/valid semantics. A transfer occurs only when `valid && ready` is true. Payload and metadata remain stable while `valid && !ready`.

## Tensor stream

- Data: 512 bits.
- Byte enable: 64 bits.
- Tag: 16 bits.
- Tensor ID: 12 bits.
- Last: 1 bit.
- Format: 4 bits (`INT4`, `INT8`, `BF16`, `FP16`, `INT32`, `FP32`).
- Tensor ID is the root descriptor index low 12 bits. Runtime software must
  prevent low-12 alias among simultaneously in-flight tensors.
- Tag `[15:4]` is command `event_signal[11:0]`; tag `[3:0]` is stream role:
  primary/K=0, secondary/V=1, bias=2, scale=3.
- `last` marks only the final accepted beat of one tensor. AHA native EOS is a
  separate 1-bit network event and is never packed into a 17-bit data lane.

## Completion/event stream

- Event ID: 16 bits.
- Status: 8 bits.
- Engine ID: 3 bits.
- Optional counter payload: 32 bits.

Event ID zero means no wait. A successful completion makes its Event ID visible
until the next reset epoch; a nonzero status never releases a wait. Runtime
software must not reuse a nonzero Event ID within one reset epoch.

Status values are: OK=0, illegal opcode/engine=1, malformed descriptor=2,
descriptor fetch error=3, unsupported policy=4, range/resource overflow=5,
watchdog timeout=6, macro/protocol error=7, KV OOM=8, stale generation=9 and
KV refcount/COW invariant failure=10. Nonzero status never releases a wait.

## Descriptor roots

Unused roots are `0xFFFFFF`; index zero is a valid descriptor. Matrix commands
use A/input/Q, B/weight/KV and C/output in src0/src1/dst. DMA uses
source/policy/destination. SFU uses primary+program/optional-secondary/output.
KV append uses K/V/metadata; gather uses metadata/NULL/output; share uses
source/NULL/destination; alloc/free use target/NULL/NULL. Barrier uses an event
list in src0 and NULL for the other roots.

Each root chain has at most 16 records. Matrix may additionally follow one
`matrix_aux.bias_index`, for an aggregate maximum of 64 cached records. All
chains are validated and snapshotted before an engine micro-operation issues.

## Matrix engine contract

The matrix engine consumes typed descriptors for `A`, `B`, optional bias/scale and `C`. It must preserve Gemmini's access/execute decoupling but must not expose RoCC or TileLink at the heterogeneous top. The first integration uses generated Gemmini RTL behind an adapter; the final implementation may refactor the Chisel generator only after equivalence is established.

## CGRA/SFU contract

The AHA island is treated as a separately generated accelerator macro. Configuration bitstreams are loaded before a segment runs. Static schedules are allowed inside the island, but all island boundaries use real ready/valid and completion events.

## KV engine contract

Logical address tuple:

`{sequence_id, layer_id, kv_head_id, logical_token, element_offset}`

Physical address is derived through the hardware block table. Page allocation, reference counting and copy-on-write are visible to the runtime through explicit commands; attention gather is a hardware streaming operation.
