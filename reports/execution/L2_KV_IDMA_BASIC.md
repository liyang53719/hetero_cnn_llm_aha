# L2 basic KV/iDMA production adapter

Result: PASS.

The schema-v2 KV adapter decodes alloc/append/gather/free root roles, KV address
and format records, BF16 tensor base/shape/stride, and drives two ordered iDMA
copies for K/V append or gather. The L2 basic profile is one sequence/layer,
one KV head, 16-token page format and head_dim <=256. Error completions carry
zero bytes and never issue iDMA requests.

Icarus randomized-ready tests perform byte-exact BF16 append and sliced gather,
free, use-after-free and missing-descriptor rejection. Core and adapter
Verilator `-Wall` lint are clean.

A production binding maps the flat request into pinned `idma_backend_rw_axi`
with 512-bit AXI, 64-bit addresses, 32-bit lengths, INCR bursts and hardware
legalization. VCS W-2024.09 copies 96 bytes in the flat smoke and runs the full
typed KV sequence through four actual iDMA requests and five completion events.
BF16 bytes match exactly; iDMA upstream remains clean.

Evidence: `work/results/l2_kv_idma_basic/` and the frozen
`idma_backend_contract_lock.json`.
