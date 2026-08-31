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
config/git_workflow_policy.json
reports/ARCHITECTURE_AND_EXECUTION_PLAN.md
reports/BRANCH_CONSOLIDATION_MAIN_ONLY.md
reports/CURRENT_WORK_BREAKDOWN_MAIN_ONLY.md
local_agent/stages.yaml
reports/execution/MASTER_LEDGER.json
reports/execution/NEXT_ACTION.json
```

The repository is **main-only**. Agents must not create local or remote work
branches, PR branches or force-push. Run `git fetch --prune origin` followed by
`scripts/check_main_only_workflow.sh` before engineering work.

L5.1 and L5.2 are closed at component/H3 scope. Current primary work is L5.3
real blocked Attention; L5.4 fused SiLU runs in parallel. L5.5 is the mandatory
Matrix/SFU/iDMA/DDR join.

```bash
./scripts/sandbox_validate.sh
./scripts/run_l5_blocked_attention_controller_e1.sh
./scripts/run_l5_silu_lut_e1.sh
```

Verilator/VCS, generated HardFloat primitives, CLN22UL DC, real iDMA/DDR,
official weights and llama.cpp/GGUF integration remain local-agent gates.
