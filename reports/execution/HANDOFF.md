# Local-agent handoff v6

Remote audit of `main` found no commit newer than `7e18aa7b0c941c65cfa053d24d75757b99008511`; the latest accepted local-agent evidence remains commit `b8f8eaff6a323a6303a52b01db6a776ddbe9e406`.

Retain the verified boundary: Block128 canonical E1 PASS (132 vectors, 32 stream beats, random backpressure), but CLN22UL 1.0 ns E4 FAIL_TIMING with WNS `-0.555804 ns` and unmapped cells 0.

Run exactly in order:

```bash
./scripts/run_l5_fp32_pipelines.sh
./scripts/run_l5_fp32_pipeline_dc.sh
./scripts/run_l5_block128_rawpipe_candidate.sh
./scripts/run_l5_block128_rawpipe_dc.sh
```

Promote `_rawpipe` only when 1024 primitive vectors, 132 Block128 vectors, 32 stream beats, random backpressure, unmapped/unresolved=0 and WNS>=0 all pass. No false path, frequency reduction or multicycle exception is authorized.

After L5.1 passes, integrate `rtl/matrix/bf16_outer_product_context_array.sv` with the real 512-lane array and close 1,000,000 dependent steps, random backpressure, II=1 across four contexts and 1 GHz timing.

Sandbox v6 has already closed the software prerequisites: Archspec collateral, 48-layer Qwen3.8 full-shape program, deterministic mock backend partition, and Sequence Memory TLB/leaf/MSHR cycle E0. Do not repeat these as local design work; use their generated contracts as test inputs.

A local push must include raw logs, result JSON, `MASTER_LEDGER.json`, `NEXT_ACTION.json`, `HANDOFF.md`, `control_plane.json`, and `stages.yaml` atomically.
