# Three-model Chisel operator primitives

This standalone project implements the model-operator sequencing layer for:

```text
Qwen2-1.5B
Qwen3.5-35B-A3B
Qwen3.8-Flash-Next
```

It is intentionally independent of Chipyard and the full Gemmini build. Each root accepts one descriptor/dimension launch, emits an ordered stream of leaf tensor operations, validates completion tag/phase/status and reports one transaction result.

## Build and test

From the repository root:

```bash
chmod +x scripts/run_three_model_operator_primitives.sh
./scripts/run_three_model_operator_primitives.sh
```

Direct SBT use:

```bash
cd chisel/three_model_operator_primitives
sbt clean compile test
sbt "runMain heteronpu.operator.OperatorProgramChecks"
sbt "runMain heteronpu.operator.EmitOperatorPrimitives ../../work/generated/three_model_operator_primitives"
```

## Protocol

`OperatorLaunch` supplies:

- sixteen typed descriptor roots;
- eight runtime dimensions;
- a transaction tag;
- runtime mode bits.

`TensorMicroOp` carries one resolved leaf phase. The root does not advance until a matching `PrimitiveCompletion` is accepted. A tag mismatch returns status `0xe1`; a phase mismatch returns `0xe2`; a nonzero leaf status terminates the root without issuing later phases.

Mode bits currently have these contracts:

```text
bit 0: GDN configured output gate uses sigmoid; clear selects SiLU
bit 1: vision merger uses post-shuffle normalization
bit 2: recurrent/decode path; clear selects prefill/chunk path
```

## Evidence boundary

Passing this project proves source-level operator coverage, elaboration and sequencing protocol behavior. It does not prove leaf arithmetic numerical correctness, descriptor/L2 integration, final RTL timing or DC/P&R closure.

The authoritative inventory and local-agent handoff are:

```text
config/model_operator_inventory_v3_complete.json
reports/LOCAL_AGENT_HANDOFF_OPERATOR_V3_800MHZ.md
plans/three_model_operator_coverage_v3_800mhz.yaml
```
