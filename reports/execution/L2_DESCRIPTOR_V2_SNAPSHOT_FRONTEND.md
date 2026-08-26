# L2 descriptor-v2 snapshot frontend

Result: PASS. `matrix_descriptor_v2_snapshot` fetches src0/src1/dst and the
optional `matrix_aux.bias_index` chain into a 64-record transaction snapshot.
It validates NULL roots, per-chain cycles and 16-record bounds, aggregate
64-record bounds, fetch errors, known record types, zero common subtype/flags
and a unique src0 matrix_aux before exposing a header or replay record.

Directed randomized-backpressure RTL fetched and replayed a legal four-chain,
14-record command only after the full snapshot completed. A cyclic src0 chain
returned malformed status 2 and replayed zero records. Byte-address mapping
remained `descriptor_base + index*16`, and held replay payload was stable.

Icarus simulation PASS. Verilator 5.050 production-module `-Wall` lint has zero
warnings. Evidence: `work/results/l2_descriptor_v2_snapshot/`.
