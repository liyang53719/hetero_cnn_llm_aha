# Model source audit v4

## Qwen3.5-35B-A3B

- Official model: `Qwen/Qwen3.5-35B-A3B`.
- Frozen config revision: `62704185bd97ad488cfc404e7caea797396b74dc`.
- Text inventory: 40 layers, 30 Gated DeltaNet, 10 full attention, 256 routed
  experts, top-8, one shared expert, 262,144 context and one MTP layer.

## Qwen3.8-Flash-Next

- Official model: `Qwen/Qwen3.8-Flash-Next`.
- Frozen model/config revision: `34567a4712bc9766c4449e2e98e4468bfa24d915`.
- Official architecture repository: `QwenLM/Qwen3.8-Flash-Next`, commit
  `513aa6e18a335296fc13e538232a8735b230877d`.
- Transformers source: `huggingface/transformers`, commit
  `36deb0b53ed0863f4b4dfdea23dcaec7f3df3701`, module
  `src/transformers/models/qwen4_exp/modeling_qwen4_exp.py`.
- Text inventory: 48 layers in `3 x linear_attention + 1 x
  qwen_sparse_attention` groups; hidden 2560; 24 Q/2 KV attention heads;
  16 QK/48 V GDN heads; 512 routed experts with top-10 plus one shared expert;
  four residual branches; PLE on layer 2; one MTP layer.

The sandbox implementation follows the official text operator boundaries but
uses deliberately tiny dimensions and deterministic generated weights. It
executes GDN, QSA, GR, PLE, routed/shared MoE and MTP state handling and freezes
hashes for regression. It does not contain or approximate the official model
weights.

Both models are multimodal. The current accelerator project targets the text
decoder only; vision remains inventory-only and unsupported.
