# Canonical architecture and execution plan v6.16

## Frozen architecture

```text
Gemmini INT8/CNN Matrix
+ Revision8B-B BF16/FP32 Matrix
+ balanced Attention/Norm/SiLU SFU
+ Stanford AHA sidecar
+ Sequence Memory and iDMA
+ shared 4 MiB SRAM
+ Command128/event fabric
```

## Qwen2 accepted boundary

- L5.1-L5.5 component, numerical, service and performance gates pass.
- L5.6a count/trace E3 passes at 320.791599 token/s.
- Official-reference checkpoints, sampled LM-head and reduced RTL anchors pass.
- L5.6d/P3 passes through a continuous llama.cpp HETERO backend equivalent: 958 graph nodes, one split, 28 layers, 588 manifest commands, 338 canonical GGUF payload bindings, zero scheduler fallback, matching argmax and Top-10.

The P3 backend is implemented as host C++/OpenMP software behind a GGML accelerator backend. It does not execute Command128 through RTL, does not use non-host device buffers and does not provide all-row RTL closure.

## Active order

```text
L9.6 full-logit metric report
  -> L9.4 one-layer 21-command RTL/device transport canary
  -> full 588-command transport, engine counts 252/308/28
  -> L9.5 non-host device buffers and removal of file staging
  -> L10.1 functional cross-owner integration
  -> L10.2 functional SRAM macro replacement
  -> L10.3 post-route PVT/OCV
  -> L10.4 workload SAIF
  -> L11 final Archspec/Pareto
```

L4 CNN/AHA, L6 low-bit, L7 production state memory and L8 Qwen3.5/Flash-Next official backends remain parallel project tracks.
