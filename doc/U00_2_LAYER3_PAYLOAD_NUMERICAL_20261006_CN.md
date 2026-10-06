# U00.2：0.8B 层3真实payload与官方decoder合成输入数值实跑

## 本轮实际完成

不是新增一层header包装：本轮实际下载并SHA256核验 Qwen3.5-0.8B 第3层全部11项权重，共36,705,280字节，加载未修改的官方 `Qwen3_5DecoderLayer`，完成完整attention+dense-FFN层的CPU forward。checkpoint固定 `2fc06364715b967f1860aea9cf38778875588b17`，Transformers固定 `14e738b5d0cc69aa27a95dde272aea41fde44f2f`，与上一轮一致。

本次输入是明确标记的确定性合成hidden-state，不是前3层产生的官方上游激活。因此结果只称 `PASS_SYNTHETIC_LAYER_SMOKE_ONLY`。U00.2保持ongoing，U01保持to do；没有生成或执行RTL，没有MAC利用率结果。

## 数值结果与边界

- 两组均为batch1、query M128；第一组past-KV=0、位置0…127，第二组past-KV=128、位置128…255。
- 两组输入不同，用绝对token偏移产生确定性序列；3个文本位置轴相同。实际传入完整additive causal mask和官方DynamicCache。已有K/V前缀逐bit不变，第二组的新V确实不同，避免重复输入掩盖stale-V错误。
- 权重原存储均为BF16。分别运行官方FP32审计配置及原生BF16配置；没有把FP32配置冒充最终硬件精度。
- FP32官方输出与独立NumPy FP64数学参考逐元素比较，2组output/K/V合计655,360元素，0不匹配。输出最大绝对误差约5.04e-7；包括K/V的最大绝对误差约1.58e-5。
- 本次软件smoke比较式在执行前固定为 `abs(actual-reference) <= 1e-4 + 1e-4*abs(reference)`。它不是已冻结的RTL或BF16逐producer比较器。
- BF16真实运行的output/K/V均有限；output相对本次FP32的最大绝对差为0.01150012（空KV）和0.01002800（已有KV）。这是诊断值，没有BF16双参考验收阈值或PASS承诺。
- “cold/warm”仅指逻辑KV为空/已有内容。未测物理权重cache、DMA、内存流量或性能冷暖条件，不能代替最终cache合同。

## 有界来源与可重放证据

`src/heteronpu/pinned_block_payload.py` 从已校验的固定header计算绝对字节范围。单次最多8MiB，11次合计36,705,280字节；没有下载完整1.747GB checkpoint，更没有下载35B checkpoint。没有重取上轮headers。

HTTP状态必须206，Content-Range/Length/Encoding必须精确匹配；先检查再读body，读取最多所需字节+1。完整payload逐tensor真实哈希保存在 `config/upstream/qwen3_5_0p8b/layer3_payload_pin.json`，该清单也由独立固定SHA256绑定。后续下载及本地加载均必须匹配，修改payload并同时伪造receipt哈希仍会拒绝。whole-file LFS哈希仍标为未本机验证。

`scripts/run_qwen35_layer3_smoke.py` 检查实际安装的官方modeling/configuration原字节、模型config摘要、固定源码ZIP URL及SHA256，严格加载全部11项参数。没有AST裁切、stub、修改官方forward或以本地重写冒充官方实现。独立NumPy参考不导入torch或Transformers。

实际使用CPU PyTorch 2.10.0及固定Transformers源码。初试PyTorch 2.5.1缺少官方依赖需要的torch.accelerator，已改为正式CPU 2.10.0；未给官方实现打兼容补丁。环境包版本、PyTorch构建信息、执行脚本实际源哈希和每个输出摘要都保存在数值回执。

本轮报告在 `reports/execution/U00_2_LAYER3_PAYLOAD_20261006/`：

- `payload_manifest.json`：每项真实字节数、范围、HTTP回执及payload摘要
- `numerical_result.json`：实际官方运行、6项全量比较、BF16诊断、KV连续性及来源
- `result.json`：回归结果、边界、归档源摘要

完整输入、官方FP32/BF16结果和NumPy FP64 output/K/V保存在本机8,689,536字节NPZ中。大权重和运行数组不塞入Git；独立CI在该精确commit重新取得固定payload、运行官方实现并上传完整NPZ及报告为Actions artifact（保留30天）。本地回执的NPZ SHA256记录于 `numerical_result.json`；跨CPU数值摘要可能不同，CI重新逐元素验证上述容差，而不伪称跨硬件bit一致。

## 复验

```sh
python -m pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e . pytest numpy==2.3.5 huggingface-hub==1.33.0 tokenizers==0.23.2 safetensors==0.8.0 'https://github.com/huggingface/transformers/archive/14e738b5d0cc69aa27a95dde272aea41fde44f2f.zip#sha256=15a8ff42ef4fba57ff51034e1cd7d3672dec2bf1cf080134eb69d13c69ee6a2d'
python scripts/collect_qwen35_layer3_payload.py --output work/new_payload
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 HF_HUB_OFFLINE=1 python scripts/run_qwen35_layer3_smoke.py --payload work/new_payload --output work/new_smoke
python -m pytest -q tests/test_pinned_block_payload.py
python -O -m pytest -q tests/test_pinned_block_payload.py
python scripts/validate_workload_evidence.py --require-complete  # 必须退出2，U00.2 OPEN
```

## 下一门禁

本轮没有关闭官方上游M128输入来源、0.8B层0 GDN真实payload/状态、Qwen2与35B完整典型层、逐producer精度/舍入双参考、真实MoE路由、实际DUT资源及性能workload集合。应继续建立真实上游输入和GDN状态链，再将同源全量数值接入实际RTL；三模型、M128、固定资源useful-wall MAC至少90%的最终目标不变。
