# Heterogeneous CNN/LLM accelerator

Architecture:

```text
retained Gemmini INT8/CNN Matrix
+ clean-room BF16/FP32 LLM Matrix
+ fixed-function Attention/Norm/SFU
+ legal Stanford AHA programmable sidecar
+ paged KV/iDMA state engine
```

Canonical control files:

```text
config/control_plane.json
reports/ARCHITECTURE_AND_EXECUTION_PLAN.md
local_agent/stages.yaml
reports/execution/MASTER_LEDGER.json
reports/execution/NEXT_ACTION.json
reports/execution/LOCAL_AGENT_WAITLIST.json
```

Sandbox progress includes Descriptor v3, universal block-128 references and RTL
source, Matrix-context protocol source, paged-KV E0, and an executable
text-only Qwen3.8-Flash-Next tiny model covering GDN, QSA, Gated Residual, PLE,
routed/shared MoE and MTP state transactions.

Run the complete sandbox gate:

```bash
./scripts/sandbox_validate.sh
```

Run the Qwen3.8 gates directly:

```bash
PYTHONPATH=src python3 scripts/run_qwen38_text_e0.py
PYTHONPATH=src python3 scripts/run_gdn_chunk_e0.py
```

Anything requiring Verilator/VCS, generated FP primitives, AHA/Chipyard,
official model weights, Synopsys DC or SRAM views is marked
`WAIT_LOCAL_AGENT_PUSH`.
