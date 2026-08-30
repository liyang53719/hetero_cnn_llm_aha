# Heterogeneous CNN/LLM accelerator

```text
Gemmini INT8/CNN Matrix
+ Revision8B-B BF16/FP32 Matrix
+ fixed-function Attention/Norm/SFU
+ Stanford AHA programmable sidecar
+ Sequence Memory Complex / iDMA
```

Current audited state:

```text
L5.1 Block128       PASS; component timing has effectively zero margin
L5.2 Matrix         PASS E1/E4 component/H3, 5-stage/5-context, H3 WNS +0.00490451 ns
L5.3 Attention      numerical/cycle/queue E0 PASS; real-stream E1/E2 next
L5.4 fused SiLU     numerical/throughput DSE PASS; 1/2-lane E1/E4 next
L5.5 integrated E3 waits for L5.3 and L5.4
```

Run sandbox regression:

```bash
./scripts/sandbox_validate.sh
```

Canonical control files:

```text
config/control_plane.json
reports/ARCHITECTURE_AND_EXECUTION_PLAN.md
local_agent/stages.yaml
reports/execution/MASTER_LEDGER.json
reports/execution/NEXT_ACTION.json
reports/execution/HANDOFF.md
```

Component/H3 DC results are not post-route signoff. Qwen3.8 software references
and policy lowering are not official-weight hardware execution.
