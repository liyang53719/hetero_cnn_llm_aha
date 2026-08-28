# L5.1 Block128 raw/round pipeline closeout

Status: PASS locally; pushed for remote audit.

- HardFloat FP32 Mul/Add elastic pipelines pass 1,024 vectors total with tag
  and stall checks (512 multiply and 512 add).
- Canonical Block128 summary merge passes 132 vectors, one complete 32-beat
  stream, and deterministic random header/beat backpressure.
- CLN22UL at 1.0 ns: Mul WNS `+0.000160873 ns`, Add WNS
  `+0.000159979 ns`, canonical Block128 WNS `+0.0000136495 ns`.
- All three DC runs have zero unmapped cells and no unresolved references.
- Canonical `fp32_mlo_summary_merge_stream` now wraps the raw/round
  implementation; the temporary alias was removed.
- Generated HardFloat RTL was emitted from Scala and was never hand edited.
  Current generated RTL SHA256 is
  `d36c11122854248d01bcf4c5c8bc6f07d9517127b34f6c1b7c6d65e89c193268`;
  canonical upstream status is clean.

This closes L5.1 only. It does not imply L5.2 or full Qwen2 performance closure.
