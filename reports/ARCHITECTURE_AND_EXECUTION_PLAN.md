# Canonical architecture and execution plan v7.1

## Frozen architecture

```text
Retained Gemmini INT8/CNN Matrix
+ Revision8B-B BF16/FP32 Matrix
+ fixed Attention/Norm/nonlinear SFU
+ Stanford AHA sidecar
+ KV and multi-domain Sequence Memory
+ shared 4 MiB SRAM
+ Command128/descriptor-v3/event fabric
+ complete three-model Chisel operator-primitive source layer
```

## Active clock policy

All new RTL generation, RTL timing parameters, DC synthesis, STA and performance projections use:

```text
800 MHz
1.250 ns
source dc/common_clock_800mhz.tcl
```

Historical 1 GHz reports remain immutable provenance only. They are not valid evidence for the active 800 MHz configuration.

At 800 MHz the nominal matrix peaks are:

```text
BF16 512 MAC/cycle       409.6 GMAC/s = 819.2 GFLOP/s
INT8 2048 MAC/cycle      1.6384 TMAC/s = 3.2768 TOPS
W4A8 4096 candidate      3.2768 TMAC/s = 6.5536 TOPS
```

Qwen2 q1024 BF16 at 300 token/s requires approximately 99.207% wall MAC utilization at 800 MHz and remains a performance-risk gate.

## Complete operator-primitive source boundary

The canonical source project is:

```text
chisel/three_model_operator_primitives
config/model_operator_inventory_v3_complete.json
```

It contains 18 independently schedulable Chisel roots and the following granular coverage:

```text
Qwen2-1.5B              30/30
Qwen3.5-35B-A3B         93/93
Qwen3.8-Flash-Next     150/150
```

The coverage includes text, vision, multimodal token injection, MTP state transactions and deterministic argmax. The source gate validates descriptor parameterization, semantic phase ordering, ready-valid backpressure and completion-error handling. It does not claim authoritative generated RTL, numerical RTL, Command128 payload integration or DC closure.

Important source corrections now frozen:

- complete Qwen3.8 hyper gate: group RMSNorm -> low-rank down -> branch scale -> SiLU -> low-rank up -> sigmoid;
- independent hyper read and write/inject roots;
- independent input embedding, final norm, LM head and MTP draft/resolve roots;
- granular vision patch/block/merge/injection roots rather than a vision placeholder;
- runtime-selectable SiLU/sigmoid GDN output gate;
- explicit PLE and QSA selection/state/sparse-gather programs.

## Qwen2 accepted backend boundary

L5.6d/P3 remains a continuous llama.cpp HETERO backend software-equivalence gate:

```text
958 graph nodes
one split
28 layers
588 manifest commands
338 canonical GGUF payload bindings
zero scheduler fallback
matching argmax and Top-10
```

The current P3 backend still executes host C++/OpenMP software behind the GGML backend. It does not execute all 588 commands through descriptor-backed RTL, does not use non-host device buffers and does not provide all-row RTL closure.

## Active execution order

```text
portable three-model Chisel source gate
  -> authoritative generation of 18 root RTL modules and required leaf modules
  -> per-root randomized ready-valid/protocol RTL simulation
  -> leaf numerical RTL closure for 30/93/150 inventory entries
  -> Qwen2/Qwen3.5/Qwen3.8/vision integration canaries
  -> Command128/descriptor/L2 owner integration
  -> 800 MHz per-root and combined-shell DC synthesis
  -> SRAM macro replacement and post-route PVT/OCV
  -> workload SAIF and final Archspec/Pareto
```

The exact local-agent tasks and acceptance criteria are in:

```text
plans/three_model_operator_coverage_v3_800mhz.yaml
reports/LOCAL_AGENT_HANDOFF_OPERATOR_V3_800MHZ.md
```
