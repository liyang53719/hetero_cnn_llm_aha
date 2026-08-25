# Frozen v0 interface contract

All block-to-block data movement uses ready/valid semantics. A transfer occurs only when `valid && ready` is true. Payload and metadata remain stable while `valid && !ready`.

## Tensor stream

- Data: 512 bits.
- Byte enable: 64 bits.
- Tag: 16 bits.
- Tensor ID: 12 bits.
- Last: 1 bit.
- Format: 4 bits (`INT4`, `INT8`, `BF16`, `FP16`, `INT32`, `FP32`).

## Completion/event stream

- Event ID: 16 bits.
- Status: 8 bits.
- Engine ID: 3 bits.
- Optional counter payload: 32 bits.

## Matrix engine contract

The matrix engine consumes typed descriptors for `A`, `B`, optional bias/scale and `C`. It must preserve Gemmini's access/execute decoupling but must not expose RoCC or TileLink at the heterogeneous top. The first integration uses generated Gemmini RTL behind an adapter; the final implementation may refactor the Chisel generator only after equivalence is established.

## CGRA/SFU contract

The AHA island is treated as a separately generated accelerator macro. Configuration bitstreams are loaded before a segment runs. Static schedules are allowed inside the island, but all island boundaries use real ready/valid and completion events.

## KV engine contract

Logical address tuple:

`{sequence_id, layer_id, kv_head_id, logical_token, element_offset}`

Physical address is derived through the hardware block table. Page allocation, reference counting and copy-on-write are visible to the runtime through explicit commands; attention gather is a hardware streaming operation.
