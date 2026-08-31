# Qwen3.5-35B-A3B and Qwen3.8-Flash-Next sandbox plan v7.3

The two models are separate architecture families.

## Qwen3.5-35B-A3B (`qwen3_5_moe`)

40 layers: 30 Gated DeltaNet plus 10 dense full-attention layers; 256 experts, top-8 and one shared expert; standard single residual stream. Sandbox work can close a tiny 3xGDN+1xfull-attention+MoE executable group, official-shape GDN recurrent/chunk parity, dense-attention output-gate vectors, 40-layer liveness/descriptor schedule and top-8 expert-cache DSE.

## Qwen3.8-Flash-Next (`qwen4_exp`)

48 layers: 36 GDN plus 12 QSA layers; four-branch gated residual, PLE, QSA index/Top-512/sparse gather, 512 experts top-10 and one shared expert. It is not Qwen3-8B or a dense Qwen3.8 variant. Sandbox work can close QSA selection vectors, PLE row-fetch/cache model, four-branch liveness, 48-layer state trace and top-10 expert-cache DSE.

## Shared

Matrix/grouped-expert engine, norm/RoPE/gate SFU, GDN state engine, MTP transaction manager, quantized frontend, policy lowering and trace/replay are shared. Dense full-attention service curves must never be substituted for QSA index scan and sparse gather.

Official-weight traces, real GGML/GGUF, RTL E1/E2, iDMA/DDR E3 and PPA remain local gates.
