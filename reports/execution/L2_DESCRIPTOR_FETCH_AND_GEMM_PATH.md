# L2 Shared-L2 descriptor fetch and production GEMM path

Decision: approved by the user on 2026-08-26. The Matrix wrapper uses one
outstanding ready/valid request carrying a 24-bit record index and receives a
128-bit record plus error. The sequencer also exposes the deterministic audit
address `descriptor_base + index*16`.

The production shell path now instantiates `gemmini_descriptor_sequencer` and
`gemmini_rocc_program_adapter`; it no longer instantiates the legacy CUSTOM_0
adapter. All three required chains are fetched and validated before the first
CUSTOM_3 issue. Null roots, missing/error responses, cycles, non-terminating
16-record chains, duplicate required records, incompatible type/shape/dtype,
and unsupported policy are rejected with zero legal RoCC issues.

The first production lowering subset is INT8 row-major single-tile
output-stationary GEMM without bias/requant. It emits the pinned official
nine-command config/load/preload/compute/store sequence and completes only
after retained Gemmini busy asserts and clears.

Measured directed results:

- descriptor sequencer: PASS, 29 reads, 9 legal ops, 3 rejected chains;
- shell/scoreboard/descriptor/program integration: PASS, 9 CUSTOM_3 commands,
  65 cycles;
- open RTL gate, structural check, macro-boundary audit: PASS;
- integrated RTL/model regression: PASS.

Evidence: `work/results/l2_descriptor_sequencer/`. This closes the approved
fetch transport and first production GEMM subset, not all of L2. Multi-tile
OS/WS, convolution, bias and requant remain to be brought through this same
production sequencer before L2 can be marked PASS.
