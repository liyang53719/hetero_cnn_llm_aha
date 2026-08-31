# Canonical architecture and execution plan v6.14

## Frozen architecture

```text
Retained Gemmini INT8/CNN Matrix
+ Revision8B-B 512-lane BF16/FP32 Matrix
+ fixed-function Attention/Norm/SFU
+ legal Stanford AHA 4×4 ratio-2 sidecar
+ Sequence Memory Complex / iDMA
+ shared 4 MiB SRAM and Command128/event fabric
```

## Qwen2 accepted boundary

```text
L5.1 Block128                              PASS
L5.2 Revision8B-B Matrix                   PASS component/H3
L5.3 Attention numerical/stress            PASS
L5.4 selected one-lane fused SiLU          PASS
L5.5 balanced 8×8 component E1/E4          PASS
L5.5 composed real-RTL E3                  PASS_REVIEW, 321.869395 token/s
L5.6a 28-layer count/trace E3              PASS, 320.791599 token/s
L5.6b official reference / LM-head sample  PASS
L5.6c reduced four-layer cross RTL         PASS, 7,840 bit-exact
L5.6d continuous 28-layer payload RTL      OPEN
```

The reduced cross-layer replay uses reference hidden snapshots at layer boundaries. It is valuable E2/E4 evidence but does not close a continuous 28-layer payload replay.

## L10 execution

L10 early PPA may run in parallel with L5.6d. The accepted pre-layout margins are extremely small; v7.8 finds six components below 1 ps and a minimum of 0.00864267 ps.

Order:

1. hierarchy-preserving integrated synthesis with explicit leaf/frozen-parent ownership;
2. reject any area roll-up that double counts a parent and its precompiled children;
3. replace/integrate SRAM macros, capacity no greater than 4 MiB;
4. measure bank/port conflicts and include macro timing arcs;
5. post-route setup/hold, PVT/OCV and design-rule closure;
6. workload-derived SAIF power.

## Full-payload numerical plan

The deterministic plan contains 168 checkpoints: six phases for each of 28 layers. Run all checkpoints, then seven continuous four-layer groups without hidden-state injection inside a group, then a continuous 28-layer replay or real-backend equivalent.

## Remaining global order

```text
L10 early PPA + L5.6d payload closure
L4 CNN/AHA
L6 low-bit parity/RTL/PPA
L7 production Sequence Memory
L8 official Qwen3.5 and Flash-Next backends
L9 real llama.cpp/GGUF
L10 post-route/PVT/SAIF
L11 final Archspec/Pareto/signoff
```
