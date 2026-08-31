# Qwen3.5-35B-A3B 与 Qwen3.8-Flash-Next 架构分离合同

## 身份边界

- **Qwen3.5-35B-A3B**：`model_type=qwen3_5_moe`，文本子模型为 `qwen3_5_moe_text`。40 层，按 3 个 Gated DeltaNet + 1 个 dense full-attention 重复；256 experts、top-8、1 shared expert；普通单 residual stream。
- **Qwen3.8-Flash-Next**：`model_type=qwen4_exp`，文本子模型为 `qwen4_exp_text`。48 层，按 3 个 Gated DeltaNet + 1 个 QSA 重复；512 experts、top-10、1 shared expert；四分支 Gated Residual；第 2 层 PLE；QSA indexer/Top-512 block/sparse gather。

Qwen3.8-Flash-Next 不是 Qwen3-8B，也不是普通 Qwen3.8 dense 架构，不能复用 dense attention 的执行图或仅改参数。

## 可共用硬件

```text
Matrix projection / grouped expert GEMM
Fixed RMSNorm / partial RoPE / sigmoid-SiLU gate SFU
GDN recurrent-state engine
MoE router / expert batching / weight cache
MTP state transaction manager
```

## Qwen3.5 专属路径

```text
Dense full-attention QKV/QK/online-softmax/PV
Standard residual add
40-layer 3:GDN + 1:full-attention schedule
256-expert top-8 scheduling
```

## Qwen3.8-Flash-Next 专属路径

```text
QSA index projection / block-summary append / streaming Top-512
Selected-token page sort/coalesce / sparse KV gather
Four-branch Gated Residual read/write and group RMSNorm
PLE n-gram hash / random row fetch / dilated depthwise-conv state
512-expert top-10 scheduling
```

## 沙箱可推进

Qwen3.5：tiny block-group E0、官方形状 GDN recurrent/chunk parity、dense-attention output-gate vectors、40-layer schedule/liveness、top-8 expert-cache DSE。

Qwen3.8-Flash-Next：QSA selection/gather vectors、PLE row-fetch/cache model、four-branch residual liveness、48-layer state trace、top-10 expert-cache DSE。

两者共用：policy lowering、trace schema/replayer、quantized frontend、state commit/rollback vectors。

## 仍需本地环境

官方权重 node trace、真实 Transformers/llama.cpp graph、RTL E1/E2、iDMA/DDR E3、CLN22UL/PPA、视觉编码器。
