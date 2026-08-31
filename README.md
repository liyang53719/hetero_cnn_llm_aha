# Heterogeneous CNN/LLM accelerator

```text
retained Gemmini INT8/CNN Matrix
+ Revision8B-B 512-lane BF16/FP32 Matrix
+ fixed-function Attention/Norm/SFU
+ legal Stanford AHA programmable sidecar
+ Sequence Memory/iDMA complex
```

Canonical controls:

```text
config/control_plane.json
config/git_workflow_policy.json
reports/BRANCH_CONSOLIDATION_MAIN_ONLY.md
reports/CURRENT_WORK_BREAKDOWN_MAIN_ONLY.md
local_agent/stages.yaml
reports/execution/MASTER_LEDGER.json
reports/execution/NEXT_ACTION.json
```

The repository is **main-only**. Agents must not create local/remote work
branches, PR branches or force-push. Run `git fetch --prune origin` and
`scripts/check_main_only_workflow.sh` before work.

Closed: L5.1 Block128, L5.2 Matrix, L5.3a controller E1/DC and L5.4 one/two-lane
candidate E1/DC. Current primary work is full Attention numerical E2; measured
Matrix-producer stall selects the SiLU lane count. L5.5 is the mandatory join.

```bash
./scripts/sandbox_validate.sh
```
