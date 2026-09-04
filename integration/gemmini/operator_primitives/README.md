# HeteroNPU Qwen-family operator primitives — 800 MHz

This package closes the **Chisel operator-primitive source layer** for:

- Qwen2-1.5B text;
- Qwen3.5-35B-A3B text and vision, including Gated DeltaNet, MoE and MTP;
- Qwen3.8-Flash-Next text and vision, including four-branch gated residual, PLE, QSA, MoE and MTP.

It reuses the existing high-throughput BF16/INT8 Matrix, Attention, fixed-SFU,
DMA/iDMA and KV arithmetic. `HeteroModelOperatorSequencer` decomposes 48 model
operators into explicit owner/opcode/variant phases. `HeteroPrimitiveLeafExpander`
then expands composite `exp`, `sigmoid`, `softplus`, `SiLU`, `GELU` and signed
square-root operations into terminal primitives. No known model operator or
terminal primitive may silently fall back.

The closure inventory is:

- 48 high-level model operator IDs;
- 25 independently emitted Chisel modules;
- 58 unique terminal owner/opcode bindings;
- Qwen2: 15 required operators, 27 terminal micro-ops;
- Qwen3.5-35B-A3B: 36 required operators, 186 terminal micro-ops;
- Qwen3.8-Flash-Next: 42 required operators, 279 terminal micro-ops;
- zero missing operators and zero unbound terminal opcodes.

Timing-oriented rules used by the new controllers:

- 800 MHz / 1.25 ns is the active synthesis target;
- Top-K is sequential and stored in `SyncReadMem`;
- runtime division/modulo use restoring division;
- runtime address products use iterative shift/add multiplication;
- GDN, convolution and PLE histories use external-state address streams;
- PLE/QSA sparse responses use tagged reorder slots;
- pending Decoupled output keeps the primitive busy until acceptance;
- unknown IDs, owners and opcodes produce an explicit error.

Run the sandbox source/semantic gate with:

```bash
integration/gemmini/operator_primitives/scripts/run_sandbox_tests.sh
```

The sandbox gate currently contains 51 tests plus a generated-RTL structural
auditor. Chisel elaboration, generated RTL simulation and DC/STA remain local
agent gates because this sandbox does not contain the pinned Scala/Chisel/CIRCT,
Verilator or proprietary standard-cell environment.

See:

- `operator_coverage_800mhz.yaml`;
- `terminal_primitive_bindings_800mhz.yaml`;
- `vectors/operator_primitives_reference_v1.json`;
- `docs/IMPLEMENTATION_PLAN_800MHZ.md`;
- `docs/LOCAL_AGENT_HANDOFF_800MHZ.md`;
- `docs/LOCAL_AGENT_ACCEPTANCE_800MHZ.yaml`.
