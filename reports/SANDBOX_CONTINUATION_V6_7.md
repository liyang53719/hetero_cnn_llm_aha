# Sandbox continuation v6.7

This increment runs independently of the unfinished local L5.3/L5.4 RTL gates.
It does not alter the accepted Revision8B-B Matrix contract.

## Closed at E0/source-reference level

1. GGML Q8_0, Q6_K, Q3_K and FP16 byte layouts, unpack/dequant and shared-dot
   operand groups. Format-specific logic stops at unpack/sign/subscale; the
   multiplier lanes and reduction tree remain shared.
2. Cross-engine speculative state transaction semantics across KV, GDN, QSA,
   PLE, hyper stream, sampler and runtime state: prefix sharing, page COW,
   per-step writes, partial-prefix commit, refcount, epoch/generation and stale
   response suppression.
3. Model-name-independent graph partition: longest supported pattern first,
   deterministic program hash and explicit CPU fallback. Synthetic Qwen2 and
   Qwen3.8 graphs are covered; vision remains fallback.
4. L5.5 discrete-event preflight for Matrix, SFU, DMA, DDR and SRAM-bank
   conflicts. This produces instrumentation and sensitivity requirements for
   the first integrated E3 run; it is not E3 evidence.

## Sandbox results

```text
Python tests                         15 PASS
Python compileall                    PASS
Independent C++20 quant vectors      384 PASS
Q8_0/Q6_K/Q3_K Python cases          2,000 per format
State transactions                   1,000 PASS
Deterministic rerun                  PASS

Analytical q1024/28-layer point:
  DDR read candidate                 100 GB/s
  SRAM banks                         16
  cycles                             3,027,331,160
  tokens/s                           338.2517
  Matrix duty                        89.558%
```

The analytical result has only about 12.8% throughput margin over the 300
token/s target. Real Attention/SiLU service curves, iDMA/DDR latency, queueing
and bank conflicts can consume that margin.

## Evidence boundary

The sandbox cannot build the pinned llama.cpp revision, Verilator/VCS RTL,
iDMA/AXI integration or CLN22UL physical views. Official quant parity, real
GGML partition, RTL E1, integrated E3 and physical E4 remain local gates.
