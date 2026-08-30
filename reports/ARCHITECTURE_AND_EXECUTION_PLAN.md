# Canonical architecture and execution plan v6.8

## Frozen architecture

```text
Gemmini INT8/CNN Matrix
+ Revision8B-B BF16/FP32 Matrix (16x32, five stage, five context)
+ fixed-function Attention/Norm/SFU
+ legal AHA 4x4 ratio-2 sidecar
+ Sequence Memory Complex / iDMA
+ 4 MiB SRAM and Command128/event fabric
```

L5.1 and L5.2 are closed only at component/H3 DC. Their very small timing
margins remain L10 post-route/PVT risks.

## Active L5 branches

- L5.3: Q16, KV32, Block128, GQA 6:1, Score/Probability FIFO 2/2, FP32 M/L/O,
  zero score/probability DDR. Real E1/E2 remains local.
- L5.4: 128-entry FP16 direct-SiLU LUT, BF16 I/O, 1/2 lane II=1 DSE. Real
  numerical/ready-valid/DC/PPA remains local.
- L5.5 starts only when L5.2/L5.3/L5.4 pass. The v6.8 sensitivity model freezes
  the required counters and a 315 t/s pre-route review floor.

## Additional source contracts

- L6: exact Q8_0/Q6_K/Q3_K/FP16 layouts and a shared 16-value operand frontend;
  no per-format multiplier arrays.
- L7: ten-domain commit barrier, epoch table, dirty-domain tracker and stale
  response filter contracts.
- L8: deterministic official node/state trace schema and offline replayer.
- L9: versioned GGML node/tensor capture ABI into the existing longest-match
  partitioner with explicit CPU fallback.

## Remaining order

```text
L5.3 + L5.4 -> L5.5 real E3 -> L5.6 q1024 >=300 t/s
L4 CNN/AHA
L6 quant RTL/PPA
L7 production Sequence Memory
L8 official Qwen3.5/Qwen3.8 backends
L9 real llama.cpp/GGUF
L10 post-route/PVT/SAIF
L11 final Archspec/Pareto
```
