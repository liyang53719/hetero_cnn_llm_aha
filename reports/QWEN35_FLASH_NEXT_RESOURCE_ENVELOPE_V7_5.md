# Qwen3.5-35B-A3B and Qwen3.8-Flash-Next resource envelope v7.5

The two models are independent architecture families and must not share a model-specific lowering contract.

## Qwen3.5-35B-A3B

```text
family                  qwen3_5_moe
layers                  30 GDN + 10 dense GQA
residual                single stream
experts                 256, top-8 + one shared
GDN FP32 state          60 MiB / sequence
Dense BF16 KV           5 GiB at 262,144 tokens
minimum staging         0.875 MiB before Matrix scratch/accumulator
active MoE traffic      601.6 MB/token at W4 without expert-cache hits
```

Required model-specific backend: dense causal GQA / Block128 Attention and standard residual handling. QSA, PLE and four-branch Gated Residual are forbidden.

## Qwen3.8-Flash-Next

```text
family                  qwen4_exp
layers                  36 GDN + 12 QSA
residual                four-branch gated residual
experts                 512, top-10 + one shared
GDN FP32 state          108 MiB / sequence
QSA BF16 KV             6 GiB at 262,144 tokens
QSA compressed index    192 MiB
Hyper tile ping-pong    640 KiB for 16 tokens
PLE row payload         5,120 bytes/token
minimum staging         1.40625 MiB before Matrix scratch/accumulator
active MoE traffic      1.379 GB/token at W4 without expert-cache hits
```

Required model-specific backends: QSA index/Top-512/sparse gather, four-branch Gated Residual, PLE sparse-row fetch and PLE convolution state.

## Shared hardware

- Matrix and grouped-expert datapath
- Norm/RoPE/gate SFU
- GDN recurrent-state engine
- Quant operand frontend
- Base expert weight-cache and route-aware prefetch
- MTP state transaction manager

All persistent GDN states and long-context KV/index structures are DDR-resident. The 4 MiB SRAM is a staging and live-tile resource, not a full-state cache.
