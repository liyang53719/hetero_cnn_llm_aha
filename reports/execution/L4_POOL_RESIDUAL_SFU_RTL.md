# L4 pool and residual SFU RTL

Status: production arithmetic RTL PASS; canonical endpoint/transport evidence
pending, so the ordered pool/residual subgate remains `IN_PROGRESS`.

`int8_pool_residual_sfu` implements signed INT8 saturating residual add and
2x2-stride2 NHWC max-pool for one 512-bit tile. Legal pool tiles support even
H/W up to 8, C up to 16 and at most 64 input bytes; larger tensors are tiled by
the controller. Output data, byte enable, tag, tensor ID, last and format remain
stable under backpressure.

The deterministic 100k gate alternates 50k residual and 50k pool operations,
covers four legal pool layouts, valid lengths 1-64, random byte enables,
198,349 positive saturations, 201,951 negative saturations and 49,955 negative
pool outputs. It passes in 750,000 cycles with output FNV-1a64
`36668a808367d67f`, zero mismatches/errors/timeouts and strict `-Wall` lint.

The next action is to expose this tile as a production SFU endpoint in the
canonical stream complex and measure physical bytes/conflicts. This report does
not mark the pool/residual subgate complete.
