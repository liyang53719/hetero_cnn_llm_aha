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
- Generated bridge/router from `8faaa7a`: both Verilator lint PASS; SHA
  `43c0f8a` / `ad073d8`.
- Eight-owner router: 2 Chisel tests PASS; every owner requires a checked
  completion and invalid owners return status 4.
- Eight real owner endpoints and 58/58 numerical bindings remain OPEN.
- Endpoint audit: candidate source roots cover 58/58, but canonical V3 payload
  adapters were 0/58. This disproves remote hardware
  closure without discarding the recovered source value.
- Control is now 1/58 PASS: real barrier waits for all domain acknowledgements,
  no early success completion; Icarus/Verilator PASS; DC WNS +0.235109 ns,
  area 646.191.
- DMA is 4/4 PASS with pinned iDMA `2e0b0fe`: 8 flat transfers and 512 bytes
  checked in VCS; 1.25 ns DC WNS +0.0000814199 ns, area 6292.65.
- Matrix is 7/7 component-bound: six BF16 opcodes use the same Revision8B-B
  16x32/5-context array; Conv adapter plus retained Rocket/Gemmini Conv1x1 PASS.
  Same-run adapter+pipeline canary remains G4.
- SFU vector 10-op subset: 16-lane/11-case numerical RTL PASS but not counted;
  DC attempt1 WNS -0.367541 ns, registered-input attempt2 timeout at 600 s with
  ~-0.35 ns snapshot. Replace dual ALUs with dedicated AddPipe/MulPipe.
- Early root DC: 18/18 PASS at 1.250 ns, min WNS +0.303001 ns, summed
  independent cell area 19590.115996; this is not combined endpoint PPA.
- Primitive DC: 23/25 PASS, min positive WNS +0.0000342131 ns, passing
  independent area 98171.164. StreamingTopK and QSA timeout at 600 s because
  the 512x65 table was flattened into ~33k registers; bind external SRAM next.
- Endpoint total 12/58 component-bound; next close 23 SFU opcodes.
