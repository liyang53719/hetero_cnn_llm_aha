# Heterogeneous CNN/LLM accelerator

```text
retained Gemmini INT8/CNN Matrix
+ clean-room BF16/FP32 LLM Matrix
+ fixed-function Attention/Norm/SFU
+ legal Stanford AHA sidecar
+ paged KV / Sequence Memory Complex
```

Current audited L5.1 state:

```text
Block128 Verilator E1        PASS: 132 vectors, 32 stream beats
CLN22UL 1 GHz E4             FAIL_TIMING: WNS=-0.555804 ns, unmapped=0
raw/round pipeline candidate source ready for local E1/E4
```

Canonical control files are `config/control_plane.json`, `local_agent/stages.yaml`, `reports/execution/MASTER_LEDGER.json`, `NEXT_ACTION.json` and `HANDOFF.md`.

Run sandbox architecture references:

```bash
PYTHONPATH=src python3 scripts/run_qwen38_architecture_e0.py
```

Run the immediate local gates:

```bash
./scripts/run_l5_fp32_pipelines.sh
./scripts/run_l5_fp32_pipeline_dc.sh
./scripts/run_l5_block128_rawpipe_candidate.sh
./scripts/run_l5_block128_rawpipe_dc.sh
```

`configs/arch_v2_qwen38_candidate.yaml` is E0-only. Official weights, new RTL E1/E2, integrated E3 cycles and E4 PPA remain explicit local gates.
