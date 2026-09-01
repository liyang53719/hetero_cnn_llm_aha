# Remote audit of `main@11483e8` and next plan

## Decision

Accept the result as a **real llama.cpp HETERO backend functional pass** and as a valid backend-equivalent route for L5.6d/P3. Reclassify the phrase “real device backend” because the current plugin uses host CPU buffers and C++/OpenMP payload execution.

## What is genuinely closed

- llama.cpp commit and model revision are pinned.
- The original 958-node graph is assigned to HETERO as one split.
- The scheduler reports zero fallback to another backend.
- All 28 layers and seven four-layer groups execute continuously without reference hidden-state injection.
- 338 GGML tensor payloads are bound to the backend contract.
- Final argmax and Top-10 set match the PyTorch reference.
- Layer-completion callback backpressure passes.

## What remains open

- Node-by-node or Command128-by-Command128 RTL execution.
- Real device memory; the plugin currently returns CPU buffer types.
- Elimination of inter-stage host files.
- Internal Matrix/SFU/KV ready-valid backpressure.
- Full-logit vector metrics.
- All-row integrated RTL and summary-storage PPA.
- Functional cross-owner top, macro replacement, post-route PVT/OCV and SAIF.

## Immediate implementation order

1. Run the new full-logit comparator on existing output files.
2. Replace one complete layer of software stage dispatch with 21 real Command128 transactions through the RTL/device path.
3. Expand to all 588 commands and assert engine counts 252/308/28.
4. Replace CPU buffers/file staging with explicit device/DMA storage.
5. Resume L10 functional integration and physical closure.

The exact acceptance criteria are machine-readable in `reports/execution/P3_BACKEND_ACCEPTANCE.json`.
