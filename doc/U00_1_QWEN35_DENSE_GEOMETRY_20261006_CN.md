# U00.1：Qwen3.5-0.8B 官方来源与 dense-FFN 几何合同

## 本次完成边界

本次仅关闭 U00.1：新增实际可执行的 0.8B profile、fail-closed 几何入口、dense 算子/状态/shape 清单、官方原字节与 tensor 名称核验。不是只增加 JSON，也不是 checkpoint 数值、实际 RTL 或 90% 利用率验收。U00.2、U00、U01 和 C03.2 继续未完成。

- checkpoint：`Qwen/Qwen3.5-0.8B`，固定 `2fc06364715b967f1860aea9cf38778875588b17`。
- 原配置 SHA256：`b90b86f35c8e6925ef74ee04d0e758f0a845c83a42089ad82bbaa948de9b4204`，2,907 字节。
- 官方 Transformers 实现独立固定为 `14e738b5d0cc69aa27a95dde272aea41fde44f2f`，modeling 文件 SHA256：`aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18`。
- 模型 revision 与实现 revision 独立固定，不声称该实现就是 checkpoint 训练时的实现。尚未执行官方 forward 或读取权重内容/header。
- `config/upstream/qwen3_5_0p8b/manifest.json` 固定 config、index、configuration、modeling、modular 五个文件的官方 URL、revision、长度和 SHA256；验证器离线核验原字节，不执行 vendored Python。

## 已落入代码的形状与语义

- hidden=1024、dense SwiGLU intermediate=3584、24 层。18 个 GDN 与 6 个 full attention，比例 3:1。
- full attention 的 0 基层索引为 3、7、11、15、19、23；典型源几何选择层 3（`B35_08_ATTN_DENSE`）和层 0（`B35_08_GDN_DENSE`），包含各自 token mixer、两次 residual 和 dense FFN。
- Q=8 heads、KV=2 heads、head_dim=256：Q 宽为 2048，K/V 各为 512；不能把 hidden1024当作Q宽。
- `q_proj` 输出宽 4096，按 `[8,512]` 每个 head 拆成 Q256 与 gate256，不能全局一刀分成前后两半。sigmoid 输出门位于 attention 结果与 output projection 之间。
- GDN K16/V16、key/value dim128、conv4；QKV conv channels=6144，value width=2048。每层 recurrent FP32 状态 1,048,576 字节，仅容量推导，不证明片上可放下。
- dense FFN 三个 BF16 权重矩阵共 22,020,096 字节；没有 router、routed/shared expert 或 MoE cache。MoE profiles 仍使用原路由合同，旧两模型 family report digest 保持不变。
- decoder/QK RMSNorm 使用 `1+weight`，GDN gated RMSNorm 使用 `weight` 与 SiLU(z)；partial RoPE=64/256。这些语义元数据、FP32 state、source identity 被明确校验。
- 所有 320 个主文本 tensor 名称与 pinned safetensors index 完全相等。index 共488项（另外153 vision、15 MTP）；shape来源为config/code推导，不能称作weight-header验证。
- vision/MTP 不加入本次典型 text block schedule。上游存在这些内容的事实保留，不宣称完整多模态/推测解码支持。

## fail-closed 与支持等级

`model_geometry.py` 显式区分 dense 与 MoE；dense 的 experts/top_k/expert_ffn 均为0，dense_ffn为正。拒绝伪造family/revision、bool冒充整数、错误shape、混入MoE/QSA/PLE/MTP、未知source/normalization/RoPE，以及超16位的packed query+gate维度。`python -O` 不会绕过检查。

`qwen_family_contracts.py` 的 inventory、states、layer_ops、schedule、summary 实际接入dense FFN，并保持历史35B/3.8行为。`model_support.py` 的入口也验证profile；dense SwiGLU完整链仍标记compiler analysis，不把已有单算子支持升级为完整block。

`qwen35_dense_contract.py` 和 `scripts/run_qwen35_dense_contract.py` 生成离线可复验报告，明确 `weights_loaded=false`、`numerical_execution=false`、`rtl_execution=false`、`mac_utilization_measured=false`、`full_U00_complete=false`。

## 回归、归档与历史保护

本次测试日志、原字节复核、几何报告和源哈希在 `reports/execution/U00_1_QWEN35_DENSE_20261006/`。精确命令/退出码/统计见 `result.json`；不能把focused pass写成全仓pass。

历史 C01.1/C03.1 已完成证据所绑定的两个 Python 源文件保存为相同字节的 `historical_sources/` 快照，原 SHA256 和证据范围不变。旧 evidence 不重新盖章为新实现通过。

35B 原pin `62704185bd97ad488cfc404e7caea797396b74dc` 的配置重新下载，SHA256为 `5e4d7f74fec2f360eb9cfbfcd6ec0c4c76e684d3a11caaed259d9fd9bfbc7944`，3544字节，几何与旧profile一致。当前可变main已移至`59d61f3ce65a6d9863b86d2e96597125219dc754`；这里只记录drift，没有替换既有pin或权重。

## 下一门禁

U00.2仍需为三个模型固定官方weight字节/header、双参考与逐producer精度、输入/初始状态、batch/query/KV、冷暖cache、真实MoE路由及实际固定Matrix/Vector资源。沿用M128作为本轮形状示例，不据此捏造整个性能测试集合已经选定。

随后将这些合同接入实际Chisel frontend/layout及完整owner状态路径，使用同源输入/权重/生成RTL，全量比较数值/状态，再对整个block从launch接受到最终输出/状态ACK（含stall、padding、drain）统计useful MAC。90%门限和固定资源分母保持不变。
