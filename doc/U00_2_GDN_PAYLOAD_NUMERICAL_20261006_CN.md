# U00.2：0.8B层0真实GDN payload与状态续算数值实跑

## 已实际完成的边界

本轮接续已完成的层3attention工作，实际取得Qwen3.5-0.8B层0全部14项权重，共43,111,008字节；运行未修改的固定官方 `Qwen3_5DecoderLayer`，包含GDN、Norm、两次residual和完整dense-FFN。checkpoint仍为 `2fc06364715b967f1860aea9cf38778875588b17`，Transformers仍为 `14e738b5d0cc69aa27a95dde272aea41fde44f2f`。

输入明确是确定性合成hidden-state，不是从官方embedding或上游模型forward提取的激活。结果只标记 `PASS_SYNTHETIC_GDN_LAYER_SMOKE_ONLY`；U00.2保持ongoing，C03.2/U01保持未关闭。没有实际RTL、MAC利用率或90%通过结果。

## 状态与数值结果

1. 主用例保持batch1/M128：cold128从空官方DynamicCache起步，carried128使用同次cold的conv和recurrent状态，输入从另一绝对token偏移生成。
2. 补充carried decode1接在上述256 token之后，覆盖官方单token causal-conv update及recurrent-rule分支。此M1仅为状态分支测试，不替代M128性能workload，也没有重定义必需性能集合。
3. 官方FP32的output、conv、recurrent与独立NumPy FP64数学参考逐元素比较，9项合计1,123,328元素，0不匹配。输出最大绝对误差8.5652e-7；包括状态的最大绝对误差2.6475e-6。
4. 比较式执行前固定为 `abs(actual-reference) <= 1e-4 + 1e-4*abs(reference)`，沿用软件数学审计口径；不声称它是已冻结的BF16或RTL逐producer精度合同。
5. 额外独立官方整段256-token回放对128+128分段结果，output和最终conv/recurrent共548,864元素通过；最大差1.1921e-7，conv缓存逐bit一致。故意清空初态后重跑第二段，输出最大差0.4394102，证明carried状态实质参与结果，避免“续算”退化为空测。
6. 独立参考采用逐token rank-one gated-delta更新，官方M128采用chunk64三角求解；没有调用torch/Transformers或复用官方chunk实现。conv缓存保持最后4个原始projected-QKV样本，carried多token前拼接完整缓存并只取最后M输出，与单token续算一致。

## 真实存储与执行dtype

层0与层3全BF16的情况不同：`linear_attn.A_log`和`linear_attn.norm.weight`在原checkpoint是F32，`dt_bias`与其余11项是BF16。下载、解码和回执保留这一区分。

- FP32审计配置将所有解码后权重提升FP32，用于上述FP64数学比较。
- 原始mixed-BF16配置用 `load_state_dict(assign=True)` 保留每个参数的真实存储dtype，不能将整个层直接 `.to(BF16)` 而损失两项F32参数精度。
- 原始mixed-BF16输入/conv-cache为BF16；官方recurrent-cache在全部三组中实际为FP32。结果逐项记录实际参数与状态dtype。
- mixed-BF16全部output/conv/recurrent均有限。相对FP32输出最大差分别0.00951457、0.01362073、0.00701320；这是诊断，无阈值或BF16双参考PASS承诺。NumPy参考的FP64状态不是实际模型状态dtype声明。

## 有界下载、来源与复验

沿用已校验的固定真实header，无需重下载header或整个1.747GB checkpoint。15次HTTP206范围读取，每次最多8MiB；12,582,912字节的in_proj_qkv分成两次，其余tensor一次。必须先核验HTTP状态、Content-Range、Length、Encoding再读body，单次最多请求长度+1。逐tensor SHA256固定于 `config/upstream/qwen3_5_0p8b/layer0_payload_pin.json`，该pin文件自身也由源中独立SHA256绑定。本机未验证whole-file LFS哈希。

runner校验实际安装的官方modeling/configuration原字节及来源archive URL/SHA256，另固定实际官方cache_utils源码SHA256；没有AST截取、stub或修改官方forward。运行脚本与实际导入参考/下载器源码摘要、包版本、PyTorch CPU构建信息一并归档。全部输入、FP32/mixed-BF16/NumPyFP64输出及conv/SSM状态以完整NPZ存于运行产物；Git仅存来源、摘要和回执。精确commit的CI重新下载真实payload、执行官方层并上传完整NPZ，保留30天。跨CPU以逐元素容差重验，不要求浮点摘要跨机器bit一致。

```sh
# 与层3相同的固定CPU运行环境：
python -m pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e . pytest numpy==2.3.5 huggingface-hub==1.33.0 tokenizers==0.23.2 safetensors==0.8.0 'https://github.com/huggingface/transformers/archive/14e738b5d0cc69aa27a95dde272aea41fde44f2f.zip#sha256=15a8ff42ef4fba57ff51034e1cd7d3672dec2bf1cf080134eb69d13c69ee6a2d'
python scripts/collect_qwen35_layer0_payload.py --output work/new_gdn_payload
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 HF_HUB_OFFLINE=1 python scripts/run_qwen35_layer0_smoke.py --payload work/new_gdn_payload --output work/new_gdn_smoke
python -m pytest -q tests/test_pinned_gdn_payload.py tests/test_qwen35_gdn_numpy_reference.py
python -O -m pytest -q tests/test_pinned_gdn_payload.py tests/test_qwen35_gdn_numpy_reference.py
python scripts/validate_workload_evidence.py --require-complete  # 仍须退出2：U00.2 OPEN
```

报告目录：`reports/execution/U00_2_GDN_PAYLOAD_20261006/`。拒绝测试覆盖错误dtype/geometry、分片顺序/缺段、重写payload并伪造receipt摘要、非有限参考输入、conv/SSM形状与状态错误；完整回归和精确命令记录于result.json。原先层3和历史合同报告不改写。

## 下一门禁

本次cold/carried只指逻辑状态，并未冻结物理权重cache、DMA或traffic条件。后续先建立可证明的官方embedding/上游M128输入与状态链；继续Qwen2和35B真实典型层、真实MoE路由及逐producer dtype/舍入双参考。随后将同源完整数值及状态接入实际生成RTL，才可用固定DUT资源、包含stall的整block wall周期测量useful MAC≥90%。本报告没有跳过这些门禁。
