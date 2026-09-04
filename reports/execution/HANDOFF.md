# Three-model operator closure handoff

- Branch: `main`; baseline: `b55ddcb`.
- Active plan: `reports/THREE_MODEL_CHISEL_RTL_DC_800MHZ_EXECUTION_PLAN.md`.
- Stage: `G3_PROTOCOL_ENDPOINT_BINDING`.
- State: `G0_G1_G2_PASS`.
- Implementation origin: Chisel; no Catapult HLS source/report exists in main.
- Frozen coverage: 18 model roots, 25 primitive modules, 58 terminal bindings.
- Models: Qwen2 30/30, Qwen3.5 93/93, Qwen3.8 150/150, plus Vision canary.
- Clock: 800 MHz / 1.250 ns, uncertainty 0.080 ns, I/O 0.100 ns.
- Library: CLN22UL base SVT TT 0.8 V 25 C.
- Resources: CPU 8-23, Java CPUs 8, Verilator j4, DC cores 8,
  MemoryHigh 24G, MemoryMax 30G, MemAvailable >10 GiB, one heavy task.
- Generated RTL must never be hand edited.
- G1 evidence: 18/18 roots, 4 Python tests, 22 ChiselTest; 25/25 modules,
  51 pytest; 58/58 bindings; canonical Gemmini clean.
- Source fixes are confined to Chisel/build scripts; generated RTL hand edits: 0.
- G2: 18 root + 25 primitive authoritative SV, one 30-module combined SV,
  0 combined/cross-layer collision, 44/44 Verilator lint PASS, no hand edits.
- G3 bridge: 53/53 kind map, 3 Chisel + 3 contract tests PASS; composite
  terminal sub-ops serialize and root completion waits for checked endpoint.
- Generated bridge from `edd8a1d`: Verilator lint PASS, SHA `a9d4317`.
- Eight-owner router: 2 Chisel tests PASS; every owner requires a checked
  completion and invalid owners return status 4.
- Eight real owner endpoints and 58/58 numerical bindings remain OPEN.
- Next: audit concrete module/port/latency mapping for all 58 bindings.
