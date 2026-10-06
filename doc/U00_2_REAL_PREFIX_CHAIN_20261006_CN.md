# U00.2：真实embedding到层3的M128官方前缀与状态链

## 本轮范围

本轮补齐Qwen3.5-0.8B层0和层3先前“从合成hidden-state起步”的来源缺口。固定checkpoint仍为 `2fc06364715b967f1860aea9cf38778875588b17`，固定Transformers仍为 `14e738b5d0cc69aa27a95dde272aea41fde44f2f`。现在从真实checkpoint embedding行进入原官方 `Qwen3_5TextModel.forward`，顺次执行GDN层0/1/2、attention层3，各层均包含Norm、residual和dense-FFN。

输入是明确冻结的人工token-ID测试夹具：256个ID按 `(73*i+19)%256` 排列，分为cold M128和carried M128。它不是自然语言数据集、tokenizer输出或模型生成结果；没有使用tokenizer，也不声称语言代表性。hidden-state则全部来自真实embedding和同次官方上游层输出，未注入合成hidden-state。

只新增下载embedding原始0至255行（524,288字节）及层1/2（各43,111,008字节），新增共86,746,304字节；层0/3复用既有已校验payload。整个前缀合计54个tensor/子区间、166,562,592字节。没有下载全checkpoint或35B大权重。embedding完整原表是BF16 `[248320,1024]`；子范围绝对字节为70216至594503，包含两端。pin同时保存原表shape、data_offsets及半开行区间 `[0,256)`。

## 官方执行边界与独立性

- 原始24层config保持不变，用meta设备构造完整TextModel，以免分配本轮不执行的层4至23及最终Norm。严格加载前4层全部真实参数，所有执行参数必须是CPU实数据。
- embedding仅替换成相同标准 `torch.nn.Embedding` 的有界真实行表，原token ID直接索引原行，不做重映射。模型本身没有embedding缩放或dropout，padding_idx为空。
- 使用未经修改的官方TextModel forward入口。官方函数生成mask、三轴RoPE并调用各decoder；层3输出hook只捕获结果后抛出专用边界异常，不改变任何数值。层4和最终Norm另有拒绝hook。不能把此过程描述为完整TextModel返回、完整模型执行或最终logits。
- 每次同一官方DynamicCache携带三层conv/FP32 recurrent及层3KV。cold M128后的状态是carried M128的真实初态。每个数组立即复制，避免后续cache原地更新覆盖证据。
- NumPy FP64参考从相同真实embedding自行运行0→1→2→3；后层只使用其自身前层输出，carried也只用其自身各层状态。没有通过插入官方中间输入或状态压低误差。GDN参考是逐token rank-one更新，独立于官方chunk64求解。
- 官方每层输入与前层输出要求逐bit一致；NumPy也检查完整链接。逐层输入、输出、conv/SSM/KV全部比较，沿用预先固定的 `abs(actual-reference) <= 1e-4 + 1e-4*abs(reference)` 数学审计门限，没有放宽。

## 状态续算与精度边界

另做官方整段256与128+128的分段等价比较，覆盖每层输入/输出及所有最终状态。对carried段逐层单独清空初态，保留其他层的cold状态和绝对位置128至255，分别验证该层自身历史及最终层3结果确实变化。KV原128项必须逐bit保持，新128项不能重复使用旧V。

真实mixed配置保留GDN各层A_log和norm.weight为F32，其余权重BF16；激活/conv/KV为BF16，三层recurrent状态始终FP32。该模式实际执行并记录对FP32差异，但不是逐producer舍入双参考PASS。NumPy状态是数学FP64，不冒充实际SSM存储类型。

所有token ID、真实embedding行、两种官方模式和独立参考的逐层输入/输出/状态，以及mask、位置、RoPE、整段重放和单层reset反事实，完整保存于NPZ。BF16实际数组以无损解码的FP32值保存，另记录原storage_dtype。Git只存来源pin、摘要及文本回执；精确提交的CI重新下载与运行，完整NPZ作为artifact保留30天。跨CPU按逐元素门限复验，不要求浮点摘要跨机器bit一致。

## 本机实跑结果

- 独立整条FP64参考：32项比较，共4,210,688个逐层输入/输出/状态元素，0不匹配。最大绝对误差2.85364e-5，最大误差/容差比0.278233；输出和状态均未剔除。
- 整段256与128+128重放：16项比较、3,219,456元素，0不匹配；最大绝对误差4.29153e-6。
- 分别清空层0/1/2/3的初态，当前层输出最大变化依次0.174505、1.209644、0.607206、0.147275；最终层3变化依次0.191472、0.516678、0.572260、0.147275。其余层初态及绝对位置保持不变。
- mixed-BF16最终层3对FP32输出最大差：cold128为0.0141953，carried128为0.0145627；均为诊断，不设事后PASS门限。
- 完整NPZ为102,980,499字节；SHA256和全部来源/数组摘要见 `reports/execution/U00_2_PREFIX_CHAIN_20261006/numerical_result.json`。测试和基线差异见同目录 `result.json`。

## 复现与验收边界

```sh
python -m pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e . pytest numpy==2.3.5 huggingface-hub==1.33.0 tokenizers==0.23.2 safetensors==0.8.0 'https://github.com/huggingface/transformers/archive/14e738b5d0cc69aa27a95dde272aea41fde44f2f.zip#sha256=15a8ff42ef4fba57ff51034e1cd7d3672dec2bf1cf080134eb69d13c69ee6a2d'
python scripts/collect_qwen35_layer0_payload.py --output work/layer0
python scripts/collect_qwen35_layer3_payload.py --output work/layer3
python scripts/collect_qwen35_prefix_payload.py --output work/prefix
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 HF_HUB_OFFLINE=1 python scripts/run_qwen35_prefix_chain.py --payload-layer0 work/layer0 --payload-layer3 work/layer3 --payload-extra work/prefix --output work/chain
python -m pytest -q tests/test_pinned_prefix_payload.py tests/test_qwen35_prefix_reference.py
python -O -m pytest -q tests/test_pinned_prefix_payload.py tests/test_qwen35_prefix_reference.py
python scripts/validate_workload_evidence.py --require-complete  # 必须退出2，U00.2 OPEN
```

下载仍采用先检查HTTP206、Content-Range/Length/Encoding再读有界body的流程；成功回执包含31次请求，单次最多8MiB。早期一次执行中断后重取前三个小tensor（合计526,400字节），所以回执字节数不等于历史总网络流量。每段及tensor摘要与源码内独立绑定的pin核对；固定fixture亦独立SHA256绑定。whole-checkpoint LFS哈希没有独立验证。官方modeling/config/cache/masking源码原字节、来源archive SHA256和实际执行包版本都记录。

U00.2保持ongoing，C03.2/U01仍未关闭。M128、原数值门限及Matrix整block useful-wall MAC≥90%目标不变；本轮没有实际RTL或利用率结果。后续门禁包括逐producer dtype/舍入双参考、Qwen2与35B真实典型block及MoE路由、物理cache/traffic和固定资源，再将同源全量数值状态接入实际RTL。不能用本次逻辑状态续算代替这些条件。
