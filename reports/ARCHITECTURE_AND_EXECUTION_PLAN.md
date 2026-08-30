# Canonical architecture and execution plan v6.6

## 1. Frozen architecture

```text
Retained Gemmini INT8/CNN Matrix path
+ Revision8B-B clean-room BF16/FP32 Matrix path
+ fixed-function Attention/Norm/SFU
+ legal Stanford AHA 4x4 ratio-2 sidecar
+ Sequence Memory Complex / iDMA
+ shared 4 MiB on-chip SRAM and Command128/event fabric
```

The current BF16 Matrix boundary is Revision8B-B:

```text
16x32 / 512 lanes
5-stage FMA
5 accumulator contexts
3-bit internal tags
5-entry completion/result buffering
1 GHz component/H3 gate
```

## 2. Accepted local closures

### L5.1 Block128

E1 and component E4 pass. WNS is only `+0.0000136495 ns`; retain as an L10
post-route/variation risk.

### L5.2 Matrix context interleave

Revision8B-B passes source contract, 1M dependent II=1, 10k random, 50k
adversarial, cross-revision compare, mapped lane compare, all component DC,
structural H3 and post-map E1.

```text
H3 WNS                     +0.00490451 ns
H3 transition/cap          0/0
H3 unmapped/unresolved     0/0
H3 area                    1661847.825806 library units
```

L5.2 is closed at the current component/H3 boundary. It is not post-route,
PVT/OCV or power signoff.

## 3. Active parallel branches

### L5.3 Blocked Attention

Frozen first implementation:

```text
Q tile 16
K/V tile 32
Block128 hierarchical M/L/O
GQA 6:1
Score FIFO 2
Probability FIFO 2
M/L/O FP32
QK and PV share Revision8B-B Matrix
score/probability DDR bytes = 0
```

Available E0 evidence:

- cycle budget and queue-depth sweep;
- BF16-input/FP32-state numerical Golden;
- q1024 analytical merge count 43,008;
- q128 full and q384/q1024 reviewed-row dense parity.

Local Agent closes real-stream E1/E2 and records the measured service curve.

### L5.4 fused SiLU(gate)*up

Frozen first candidates:

```text
128-entry FP16 direct-SiLU LUT
linear interpolation
BF16 input/output
II=1
1-lane and 2-lane implementations
```

Use producer-stall <=2% as the selection rule. Do not build 4/8 lanes unless
measured evidence requires them.

### L5.5 join

L5.5 integrated Matrix/SFU/iDMA/DDR E3 begins only after L5.2, L5.3 and L5.4
pass. L5.2 is now complete; L5.3 and L5.4 are open.

## 4. Additional sandbox closures

### Sequence Memory

Concurrent E0 now includes TLB, leaf cache, bounded MSHRs, same-page miss
coalescing, out-of-order device completion, in-order retirement and stale
generation suppression. First RTL point: 8 MSHRs and 16 data requests
outstanding. AXI/iDMA E3 remains local work.

### Qwen3.8 compiler path

The full 48-layer model is lowered deterministically into one Command128
segment per layer. Current result: 48 segments, 1648 commands, 48 barriers,
36 GDN layers and 12 QSA layers. Real GGML graph matching, GGUF tensor binding,
device submission and CPU fallback remain L9 work.

## 5. Remaining global order

```text
L4 CNN/AHA E1/E4
L5.3 Attention E1/E2 ┐
L5.4 SiLU E1/E4      ├→ L5.5 integrated E3 → L5.6 q1024 >=300 t/s
L5.2 PASS            ┘
→ L6 exact GGML quant formats and low-bit RTL
→ L7 production Sequence Memory E1/E3
→ L8 Qwen3.5/Qwen3.8 official trace and backends
→ L9 real llama.cpp/GGUF backend
→ L10 SRAM/post-route/PVT/SAIF
→ L11 final Archspec/Pareto signoff
```
