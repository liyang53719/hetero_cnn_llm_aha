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
- Matrix now has one atomic owner: 7-op protocol PASS. Hierarchical final link
  uses the real 3.1M-leaf Revision8B-B DDC and Conv adapter: WNS +0.256689 ns,
  area 1662370.985, 0 error/unmapped. Existing 3877 transition/46 fanout
  violations remain explicit and prevent a physical-clean claim.
- SFU vector 12/23: 16-lane/13-case numerical PASS. The old DC result was
  invalidated by LINK-3 tag-width errors; corrected clean-log DC is WNS
  +0.000015974 ns, area 68156.816, 0 unmapped/error.
- ReduceMax16 stable/NaN/tie and ReduceSum16 numerical+owner mux PASS;
  corrected clean-log ReduceSum DC WNS +0.0000216961 ns, area 11589.487.
- Rsqrt/Reciprocal/Exp2 local replay: 10k vectors each PASS at Verilator j4;
  max relative errors 2.39e-7 / 9.19e-7 / 2.35e-4. V3 owner mux open.
- Scalar V3 endpoint for Rsqrt/Reciprocal/Exp2 now waits for real module output
  and passes protocol smoke; SFU functional coverage 15/23. Rsqrt switched to
  NR2 Add/Mul pipelines and passes 1.0 ns DC (+0.000101328 ns, area 4136.31403).
  Original Reciprocal optimized empty and Exp2 WNS -0.140313 ns.
- Reciprocal NR2 now passes the original 10k vectors and 1.25 ns DC: WNS
  +0.0000582933 ns, area 3664.843, 0 unmapped; scalar endpoint regression PASS.
- Exp2 sequential MulPipe/AddPipe now passes original 10k vectors and DC:
  WNS +0.0000697374 ns, area 4486.3. Scalar 3-op flat DC passes with common
  HardFloat source: WNS +0.0000766516 ns, area 11890.515, 0 unmapped.
- SFU scalar numerical+endpoint+DC coverage reached 15/23 before Norm.
- Qwen2 RMSNorm1536 revalidated after ReduceSum pipeline: 1000 vectors PASS,
  1,829,998 cycles, max reference error 8.84e-7.
- Shared Norm16 core now binds RMSNorm and L2Norm through one V3 endpoint;
  numerical smoke and DC PASS, WNS +0.000175953 ns, area 13539.162.
- RMS/L2 were the initial two-mode checkpoint; superseded by four-mode Norm.
- RMS/GroupRMS/L2/LayerNorm now share exactly one physical Norm16 core.
  Four-mode test PASS; final clean-log DC WNS +0.00000369549 ns, area 80524.626,
  0 unmapped/error. LayerNorm includes real mean/variance/weight/bias. SFU 19/23.
- RoPE pipeline matches 10k frozen vectors; 512-bit endpoint passes 100
  transactions/800 pairs. Clean-log DC WNS +0.0000354052 ns, area 14114.1.
  SFU reached 20/23.
- OnlineSoftmax binds block32 local weights plus merge128 summary variants;
  legacy token-chain is unused. Endpoint, 132 merge vectors and compliant j4
  q128/q384/q1024 8-seed protocol PASS. DC WNS +0.0000165701 ns, area
  51283.232, 0 unmapped/error. SFU reached 21/23.
- Gate binds the fixed 8-lane BF16 fused SiLU-times-up array: 4096 frozen
  vectors/32768 lane-pairs and 100 endpoint transactions PASS. Registered input
  boundary DC: WNS +0.00021565 ns, area 80192.84, 0 transition/error/unmapped.
  SFU reached 22/23.
- Pwl variants are frozen to Softplus=1 and tanh-GELU=2. Generated 128-segment
  tables pass 20k vectors at max error 0.0019444/0.0015513; endpoint PASS.
  DC WNS +0.0000449419 ns, area 7439.978, 0 error/unmapped; five near-zero
  transition violations remain visible. All 23 SFU component endpoints exist.
- SFU owner atomically dispatches all 23 opcodes to seven checked children.
  23-op + invalid regression PASS. Flattened-child DC after Gate boundary fix:
  WNS +0.00000369549 ns, area 314488.629, 0 error/unmapped; 17 near-zero
  transition violations remain reported. SFU owner is PASS.
- KV owner binds append/gather/alloc/free to a two-level 10+10-bit DDR page
  resolver, 128-bit PTE and external allocator/iDMA. 101 successful commands
  include q1024/64 pages; stale generation and invalid opcode pass. DC WNS
  +0.0000463724 ns, area 7436.702, 0 error/unmapped. Advanced L7 COW/TLB open.
- State owner uses authoritative HeteroStateTransaction plus a fixed 16x512-bit
  journal and one shared FP32 mul/add for decay/conv4. All 7 opcodes pass 104
  commands including commit/rollback. DC WNS +0.0000886917 ns, area 48604.283,
  0 error/unmapped; 117 near-zero transition violations remain visible.
- Selection owner closes TopK/Expand/Route/Merge/BlockPool/MTP over 100
  transactions. TopK uses an external 512x65 SRAM port, so no flattened table
  remains. DC WNS +0.000525236 ns, area 29113.357, 0 error/unmapped/DRC.
- Vision owner closes six generated address/layout controllers over 100
  transactions. Chisel fixes make helper names/ports stable and pipeline the
  Patch3D carry chain; generated SV was regenerated, never edited. Owner DC
  WNS +0.000558019 ns, area 14857.843, 0 error/unmapped.
- Early root DC: 18/18 PASS at 1.250 ns, min WNS +0.303001 ns, summed
  independent cell area 19590.115996; this is not combined endpoint PPA.
- Primitive DC: 23/25 PASS, min positive WNS +0.0000342131 ns, passing
  independent area 98171.164. StreamingTopK and QSA timeout at 600 s because
  the 512x65 table was flattened into ~33k registers; bind external SRAM next.
- Endpoint adapters are 58/58. This is not G3/model closure: connect all eight
  owners to the terminal router, run four model canaries, then combined-shell DC.
- Generated endpoint-bound eight-owner shell lifts every payload/config/memory
  port; structural lint PASS. Final linked DC includes Router, all owners and
  real Revision8B-B: WNS +0.00000369549 ns, area 2085007.384, 0 error/unmapped.
  4056 transition/47 fanout violations and four root canaries remain open.
- Root Bridge is now ahead of that shell: linked DC WNS +0.00000369549 ns,
  area 2085711.542, 0 error/unmapped. Canary blocker is internal composite
  scratch chaining in SFU; protocol-only leaf completion is not numerical PASS.
- SFU now has fixed 10x512 scratch chaining. Bridge Softplus/GELU/Sigmoid/SiLU
  numerical tests PASS (1/1/8/9 leaves); final result precedes completion.
  Scratch SFU DC WNS +0.00000369549 ns, area 326007.318. Previous combined
  report was superseded and has now been rerun.
- Maintenance- and scratch-enabled full root shell linked DC PASS: WNS
  +0.00000369549 ns, area 2097406.589, 0 error/unmapped; 4058 transition/47
  fanout violations. The maintenance wrapper supersedes the prior root DDC.
- Qwen2 decoder root canary remains PASS 26/26 after protocol regeneration.
  MTP now carries an internal successful-completion predicate and issues exactly
  one commit or rollback; MoE RoutedExpert scatter now selects route dispatch.
  Root tests 24/24 and Bridge/Router tests 6/6 PASS; Qwen3.5 integrated canary
  and post-change Selection/root/combined DC are next.
