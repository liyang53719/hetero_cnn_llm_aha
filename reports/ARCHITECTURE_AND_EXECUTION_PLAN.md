# Canonical architecture and execution plan v6.9

## Frozen architecture

```text
Retained Gemmini INT8/CNN Matrix path
+ Revision8B-B clean-room BF16/FP32 Matrix path
+ fixed-function Attention/Norm/SFU
+ legal Stanford AHA 4x4 ratio-2 sidecar
+ Sequence Memory Complex / iDMA
+ shared 4 MiB SRAM and Command128/event fabric
```

The BF16 Matrix boundary remains frozen at 16x32, 512 lanes, five FMA stages, five accumulator contexts and a depth-five completion FIFO. L5.2 is closed at component/H3 DC; it is not post-route signoff.

## Active L5 branches

### L5.3 Blocked Attention

```text
Q tile 16, K/V tile 32, Block128, GQA 6:1
Score FIFO 2, Probability FIFO 2
FP32 M/L/O
QK and PV share Revision8B-B Matrix
score/probability DDR materialization = 0
```

Available E0/source artifacts now include dense-vs-blocked numerical Golden, cycle and queue-depth models, a command-order/controller protocol model, and synthesizable controller RTL/TB/E1/DC scripts. The controller protocol is a subgate. L5.3 closes only after the real Matrix and Block128 SFU datapaths pass q128/q384/q1024 numerical E2 and measured service E1 under random backpressure.

### L5.4 fused SiLU(gate)*up

```text
128-entry FP16 direct-SiLU ROM over [-8,8]
Q12 linear-interpolation fraction
shared generated FP32 add/mul pipelines
BF16 input/output, II=1
one-lane and two-lane candidates
```

A bit-oriented Golden, ROM, synthesizable lane/array/tops, vector generator, testbench and E1/DC scripts are source-ready. Select one lane if the measured Matrix producer stall is <=2%; otherwise select two lanes.

### L5.5 join

L5.5 starts only after L5.2, full L5.3 and L5.4 pass. The analytical preflight is not E3. Replace all Attention/SiLU durations with measured service curves and collect DDR, queue, bank and event counters. Reopen the performance budget when the pre-route projection is below 315 token/s.

## Remaining order

```text
L4 CNN/AHA E1/E4
L5.3 full Attention E1/E2 ┐
L5.4 fused SiLU E1/E4     ├→ L5.5 integrated E3 → L5.6 q1024 >=300 t/s
L5.2 PASS                 ┘
L6 pinned GGML parity and low-bit RTL
L7 production Sequence Memory E1/E3
L8 Qwen3.5/Qwen3.8 official traces and backends
L9 real llama.cpp/GGUF backend
L10 SRAM/post-route/PVT/SAIF
L11 final Archspec/Pareto signoff
```
