# 独立 QKV block/pair recipe：准备阶段

## 中文计划

- 已定位：run38918003722 的 native128 原始独立 NumPy gate 失败于 gate、scores、logits、prob；所有 BF16/FP32 语义检查通过。n0、cos、sin 位精确，最早差异在 Q/K/V 投影。
- 已完成：17项普通 / -O 冷测试，以及真实严格 C++ 编译和7个对抗性lane的4096字微型数值验证。首次微型验证耗时0.848871275秒，编译/kernel均exit0；包含无效输入、别名与舍入模式拒绝。
- 待执行：使用真实原始输入分别执行 fresh M16、M128 全阶段 native gate。只有两者原有门槛全部通过，才能推进 PublicExecution。
- 不确定：下游 NumPy QK/PV/MLP reduction 是否仍有差异；任何后续失败继续保留，不能保证此次 QKV 对齐关闭所有门槛。

## 已有证据与边界

失败 ZIP SHA-256：`bd737254f9a61d53ef7cd271553b52872dd497f6f78ec142cbac473c1105ef0a`；原始 native RESULT SHA-256：`1ded813cfa4b0d96b04a334375a69d52699044e7af05c737616c76b96f002e33`。

BF16 max_abs：gate 0.041015625、scores 16、logits 8、prob 0.031494140625；operator 门槛仍为0.03125，mean_abs 均通过。输出 y max_abs 0.015625，通过原block门槛。相同输入的 n0 已位精确，而 qr/kr/v 分别产生0.0078125、0.0009765625、0.00048828125最大差异，说明不能把后续误差直接归因于 KV 借用。

历史38b943cd完整链报告明确保存同四项 auxiliary_independent_producer FAIL，同时 official observed gate PASS。旧记录的 causal scores覆盖与此次全矩阵 scores不同，不能混用数值。此次继续保留严格的 native 全阶段验收，不恢复较弱的历史准入。

## 唯一算术变化

复用现有 `dense_block_reduce/reference/dot16.inc` 和已固定的 profile.json，不读取或复用任何官方输出。独立路径使用自己的 n0、原始权重和bias：

1. K1536分为1024和512两个独立FP32累加块。
2. 每个BF16 pair按高索引、低索引顺序执行显式FP32 FMA。
3. 两块分别完成后执行一次FP32合并，再单独加bias。
4. 最后仅一次BF16 ties-to-even物化。

已有profile记录原CPU/oneDNN实现下M16、M128的六个QKV fixture匹配；这不是当前新构建或新机器的数值PASS。新实现必须重新对比真实 native 结果。

原始 `scripts/qwen2_layer0_model_gate.py` 完全保留。source-only preparer在新目录生成显式变体，仅为独立BF16 Q/K/V调用添加 `qkv_recipe`；默认None回到原NumPy路径。FP32诊断、官方PyTorch forward、其他独立算子、原始阈值、全29阶段清单与语义gate均不改变。独立QKV不接受官方activation、cache或output注入。

Recipe必须显式加载已验证的库凭据；来源、编译参数、库字节及加载模块身份前后复核。新recipe身份进入原run_gate runtime identity，因此原M128 small_gate校验要求同recipe的fresh M16，而不能继承旧NumPy M16。编译及真正数值执行均为opt-in；本批没有接入现有setup/CI，也没有改变任何旧profile或历史凭据。

## 来源检查与准备测试

`pins.json`分别固定原始module、现有dot16/profile/spec、新适配器/构建器/测试、patch与精确生成字节。AST检查证明禁用路径投影与原始源码一致；启用路径由直接代码审查与生成哈希约束，不能把AST投影当成完整数值证明。

```sh
python -m unittest candidates.qwen2_resident_matrix.raw_kv_native_qkv.test_recipe -q
python -O -m unittest candidates.qwen2_resident_matrix.raw_kv_native_qkv.test_recipe -q
```

冷测试使用独立精确Fraction微型fixture覆盖pair顺序、block边界、bias与BF16 tie；控制测试使用明确标记的mock接口，不伪称本地C++或真实权重已经执行。没有新增SRAM/MAC、RTL或硬件性能结论。

独立微型验证入口为 `test_recipe.run_native_smoke(out)`，仅在显式调用时构建严格小库并以合成的 M16/K1536/N256 数据检查全部4096输出字。一次总期限为30秒；安全报告包含退出状态、固定fixture计数、来源/库/输出摘要，不包含数组。它只能证明这些微型fixture，不能代替真实权重的M16/M128门槛。

已验证微型结果的输出SHA-256为`77ce3dca42c029a84c6c7a076e9ec8e80c30ed9597f1f8773b85cdea636549df`，库SHA-256为`7a2f827649eba6fbf836c28904fbeed198a171694b2f26cbe28782a9ac1890a9`。安全结果保存在同目录 `SMOKE_EVIDENCE.json`；该非执行证据不参与构建来源闭包，避免结果与自身来源形成循环。完整native M16/M128仍未运行。
