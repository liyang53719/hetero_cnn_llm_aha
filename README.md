# Heterogeneous CNN/LLM accelerator

```text
retained Gemmini INT8/CNN Matrix
+ Revision8B-B 512-lane BF16/FP32 Matrix
+ fixed-function Attention/Norm/SFU
+ legal Stanford AHA programmable sidecar
+ Sequence Memory/iDMA complex
```

Canonical control files:

```text
config/control_plane.json
reports/ARCHITECTURE_AND_EXECUTION_PLAN.md
local_agent/stages.yaml
reports/execution/MASTER_LEDGER.json
reports/execution/NEXT_ACTION.json
```

L5.1 and L5.2 are closed at component/H3 scope. Current primary work is L5.3 real blocked Attention; L5.4 fused SiLU runs in parallel. v6.9 adds a source-ready Attention command controller and source-ready one/two-lane fused SiLU datapaths.

```bash
./scripts/sandbox_validate.sh
./scripts/run_l5_blocked_attention_controller_e1.sh
./scripts/run_l5_silu_lut_e1.sh
```

Verilator/VCS, generated HardFloat primitives, CLN22UL DC, real iDMA/DDR, official weights and llama.cpp/GGUF integration remain local-agent gates.
