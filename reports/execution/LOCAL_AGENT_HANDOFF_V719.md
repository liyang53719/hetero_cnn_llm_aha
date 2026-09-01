# Local-agent handoff v7.19 — main only

## Accepted boundary

The `11483e8` result closes the **real llama.cpp backend-equivalent functional route** for Qwen2 q1024:

```text
original llama graph       958 nodes
backend splits             1
scheduler fallback         0
continuous layers          28
four-layer groups          7
canonical payload bindings 338
raw GGUF byte-preserving   281
F32->BF16 RNE conversions   57
manifest Command128        588
argmax                     7559
Top-10 overlap             10/10
layer completion stalls    7
```

This is not a hardware-device or all-row RTL closure. The HETERO plugin uses host CPU buffers, intercepts the whole graph in `graph_compute`, calls `hetero_qwen2_submit_588`, and runs the generic C++/OpenMP payload backend. The command files are validated, not interpreted by the RTL command frontend. The seven stalls are completion-callback stalls.

## First commands

```bash
git fetch --prune origin
git checkout main
git pull --ff-only origin main
./scripts/check_main_only_workflow.sh
./scripts/sandbox_validate.sh
python3 scripts/audit_p3_backend_evidence.py
```

Do not create a branch and do not force-push.

## P0 — full-logit report

Run:

```bash
python3 scripts/compare_p3_logits.py \
  --actual work/results/llama_hetero_full_graph/logits.bin \
  --reference work/results/llama_cpp_qwen2_baseline/pytorch_logits.bin \
  --output reports/execution/l5_6d_p3_full_logits_result.json
```

Acceptance:

```text
finite mask equal
argmax equal
top-10 overlap 10/10
relative L2 <= 0.01
cosine >= 0.9999
```

Commit the complete metrics, thresholds and raw-file hashes.

## P1 — real Command128 transport canary

Replace the software stage-dispatch path for one complete layer with:

```text
588-plan subset
  -> RTL command/event frontend
  -> descriptor fetch
  -> iDMA / Shared L2
  -> Matrix / Attention SFU / Norm / SiLU
  -> completion/event return
```

The canary must not call `qwen2_generic_layer_embedded_main`, must not use host files as inter-stage tensor transport, and must expose non-host or explicit DMA-backed device buffers.

Acceptance:

```text
21 unique layer commands accepted/completed
no loss/duplicate/reorder/event error
internal Matrix/SFU/KV random ready/valid stalls > 0
all six payload phases execute on real engines
no hidden-state injection inside the layer
output vs official layer checkpoint PASS
```

## P2 — expand to all 588 commands

Acceptance:

```text
commands accepted/completed 588/588
engine counts Matrix/SFU/KV 252/308/28
28 layer completions
7 four-layer groups
internal backpressure, not only completion callback stalls
GGUF tensor binding without host-file staging
final full-logit acceptance PASS
```

## Parallel physical gates

The retained frozen-DDC and standalone SRAM inventories remain useful preflight only. Still required:

```text
functional cross-owner integrated top
100% logical-RAM -> SRAM-macro replacement
SRAM LEF/GDS physical views
post-route setup/hold and PVT/OCV
workload-derived SAIF power
summary-storage macro mapping and PPA
```

ARM `bifrun`/memory-compiler failures remain a local physical-view blocker. Preserve all raw logs and tool/library hashes.
