# Qwen3.8 sandbox and local-dependent advance

The retained local Block128 E1 passes; E4 fails at WNS `-0.555804 ns`. This change does not overwrite that evidence.

New E0 work:

- append-time QSA block summary and bounded streaming Top-512, 200 random parity cases, zero selection mismatch, zero full-score materialization;
- selected-token page sorting/coalescing with exact restore order;
- 1,000 randomized MTP accepted-prefix transactions across GDN, QSA, PLE, KV and hyper-stream state;
- full-shape MAC/state/DDR lower bounds;
- synthetic PLE row-cache and MoE expert-cache/batching DSE;
- FP32/BF16/FP16/FP8/INT8 stability screening;
- 4 MiB interval-liveness candidate;
- four-context Matrix cycle model: 1,000,000 dependent operations in 1,000,003 cycles and 10,000 random backpressure operations.

Local-dependent source added:

- HardFloat multiply/add split at the native raw/round boundary;
- 1024-vector random-backpressure primitive gate;
- `_rawpipe` Block128 coefficient/beat/stream candidate;
- parameterized context wrapper around the existing 16x32 BF16 array;
- Verilator and CLN22UL scripts.

None of the new hardware source is called E1/E4 until the commands in `NEXT_ACTION.json` pass.
