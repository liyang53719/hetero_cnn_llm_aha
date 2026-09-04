# Local-agent handoff: Chisel elaboration, RTL simulation and DC at 800 MHz

## Immutable starting point

Use the repository `main` commit containing this document. Do not create a new
branch, force-push, edit generated RTL manually, or delete sandbox/local build
artifacts. Preserve all logs and intermediate directories as evidence.

The accepted sandbox boundary is source/semantic closure only: 48 high-level
operators, 25 catalog modules, 58 terminal bindings and zero missing/unbound
items. Generated RTL, RTL simulation and physical evidence remain open.

## T0 — reproduce source-level gates

```bash
integration/gemmini/operator_primitives/scripts/run_sandbox_tests.sh
```

Acceptance:

- at least 51 pytest tests, zero failures;
- JSON status `PASS_OPERATOR_PRIMITIVE_COVERAGE`;
- operator IDs = 48, catalog modules = 25, terminal bindings = 58;
- model terminal counts = 27 / 186 / 279;
- all model `missing` and `unbound_terminal_opcodes` lists are empty;
- shell syntax and `git diff --check` pass.

## T1 — elaborate every Chisel primitive

Use the pinned Gemmini/Chisel/CIRCT checkout already used by the existing
HardFloat emitters. Export its path and run:

```bash
PINNED_GEMMINI_DIR=/absolute/path/to/pinned-gemmini \
OUT_DIR=work/generated/operator_primitives_800mhz \
  integration/gemmini/operator_primitives/scripts/generate_all_primitives.sh
```

Acceptance:

- exactly 25 catalog modules emit non-empty SystemVerilog;
- `verify_generated_rtl.py` returns PASS;
- zero FIRRTL/Chisel exceptions, width errors, uninitialized signals or
  combinational-loop diagnostics;
- catalog order, source SHA-256, emitted RTL SHA-256, repository commit,
  Gemmini commit, Java version, SBT version and logs are preserved;
- generated files are not edited manually.

## T2 — randomized Chisel/RTL differential simulation

Compare emitted RTL against `reference/operator_primitives_reference.py` and
`vectors/operator_primitives_reference_v1.json`. Regenerate with
`scripts/generate_reference_vectors.py` and require byte-for-byte equality before simulation. Exercise:

- arbitrary input/output backpressure and same-cycle request/response;
- reset/clear during idle and after completed transactions;
- Top-K FP32 ties, infinities, signed zero and NaNs;
- QSA K=512, compression ratio 4 and every tail length;
- PLE 16 heads, n-gram 3, iterative modulo and OOO row responses;
- MoE Top-8/Top-10, shared expert and arbitrary completion order;
- official GDN head/dimension address spaces without allocating register arrays;
- causal convolution kernel 4 and PLE dilation 3;
- MTP all-match and every first-mismatch position;
- odd vision grids, padding, 2x2 merge and destination-size-one interpolation;
- output backpressure while `busy` remains asserted.

Acceptance: sequence/bit exact, zero loss/duplicate/reorder/protocol assertions,
and at least one observed stall on each Decoupled interface.

## T3 — bind terminal arithmetic endpoints

Use `terminal_primitive_bindings_800mhz.yaml` as the sole owner/opcode checklist.
Bind every terminal micro-op to existing Matrix, fixed SFU, DMA/iDMA, KV,
state-memory, selection or vision endpoint. Hardware remains model-name
agnostic; shapes and policies come from descriptors.

Acceptance:

- 58/58 unique terminal bindings connected;
- unsupported owner/opcode = 0 and CPU fallback = 0 for all 48 IDs;
- composite activation opcodes never reach the terminal frontend;
- GDN/QSA/PLE persistent state uses SRAM/DDR;
- Top-K and reorder structures infer/map to memory where intended;
- terminal frontend preserves parent operator/opcode/phase/variant provenance.

## T4 — DC synthesis and STA at 800 MHz

Every active run must source `dc/operator_primitives_800mhz.tcl` and call
`hetero_apply_800mhz_constraints`. Do not use an active 1.0 ns clock.

Acceptance per module and integrated primitive shell:

- period = 1.25 ns;
- setup WNS >= 0.00 ns and hold WNS >= 0.00 ns at required corners;
- zero unconstrained endpoints and inferred latches;
- no combinational runtime divider/modulo and no 512-way sorter;
- no GDN/PLE history or recurrent matrix inferred as large register arrays;
- memory, register, multiplier, area and timing reports present;
- reports bind repository commit, tool version, standard-cell library, PVT
  corner, constraint SHA-256 and log SHA-256.

A failed module must remain failed in the report; do not weaken constraints or
remove ports to obtain a green status.

## T5 — commit and push directly to main

Commit generated evidence, reports and any source fixes directly to `main`.
Rerun T0–T4, pull/rebase if needed, push without force, and prove:

```bash
test "$(git branch --show-current)" = main
test "$(git rev-parse HEAD)" = "$(git ls-remote origin refs/heads/main | cut -f1)"
```
