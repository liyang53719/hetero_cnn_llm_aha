# L5 pinned Qwen target-shape lock

Status: PASS for provenance, operator policy and array-step derivation; no
target-shape RTL cycles or payload numerics are claimed yet.

The canonical source is `Qwen/Qwen2-1.5B-Instruct` at revision
`ba1cf1846d7df0a0591d6c00649f57e798519da8`. The downloaded `config.json`
SHA256 is `a58e896d2756a7947f23f3db55667c19ca3b8524188a30c8c640cd7ff72a5136`;
the Apache-2.0 LICENSE SHA256 is
`c156170b718ec29139d3653d40ed1986fd92fb7e0959b5c71f3c48f62e6636f4`.

The frozen target is hidden1536, intermediate8960, 12 query heads, two KV
heads, six query heads per KV head and head dimension 128. RMS epsilon is
`1e-6`, RoPE theta is `1e6`, and sliding-window attention is disabled. The
FP32 attention scale is `0x3db504f3`.

The config declares Transformers 4.40.1. Its pinned official Qwen2 source was
hashed and audited: Q/K/V projections have bias; OProj and gate/up/down do not.
The GQA mapping is query heads 0-5 to KV head 0 and heads 6-11 to KV head 1.

On the physical 16x32 BF16 array, one complete target token requires 1,462,272
array steps. The two-token compact gate adds one previous-token K and V and
therefore requires 1,486,848 steps. A serialized four-cycle-per-step value of
5,947,392 is recorded only as an analytical schedule projection, never as an
RTL measurement. Dense BF16 weights for the seven matrices total 46,792,704
elements or 93,585,408 bytes.
