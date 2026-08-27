# Heterogeneous CNN/LLM accelerator

```text
retained Gemmini INT8/CNN Matrix
+ clean-room BF16/FP32 LLM Matrix
+ fixed-function Attention/Norm/SFU
+ legal Stanford AHA sidecar
+ paged KV / Sequence Memory Complex
```

Current audited L5.1 boundary:

```text
Block128 Verilator E1        PASS: 132 vectors, 32 stream beats
CLN22UL 1 GHz E4             FAIL_TIMING: WNS=-0.555804 ns, unmapped=0
newer local-agent push       not present at the v6 audit base
raw/round pipeline           source ready; local E1/E4 required
```

Sandbox v6 additionally closes the following E0/compiler prerequisites:

```text
Archspec inheritance, validation and deterministic collateral generation
Qwen3.8 48-layer full-shape prefill/decode program with MAC/byte accounting
Qwen3.8 deterministic mock backend partition, policy bindings and event program
Sequence Memory TLB/leaf-cache translation and COW-cost model
control-plane cross-file consistency audit
```

Run the complete sandbox gate:

```bash
./scripts/sandbox_validate.sh
```

Run the v6 planning/compiler/cycle generator:

```bash
PYTHONPATH=src python3 scripts/run_planning_v6.py
```

The immediate local-agent critical path remains:

```bash
./scripts/run_l5_fp32_pipelines.sh
./scripts/run_l5_fp32_pipeline_dc.sh
./scripts/run_l5_block128_rawpipe_candidate.sh
./scripts/run_l5_block128_rawpipe_dc.sh
```

`configs/arch_v2_qwen38_candidate.yaml` remains non-canonical. Shape-only lowering, mock scheduling and cycle-structured E0 models are not official-weight execution, RTL E1, integrated E3, or E4 PPA evidence.
