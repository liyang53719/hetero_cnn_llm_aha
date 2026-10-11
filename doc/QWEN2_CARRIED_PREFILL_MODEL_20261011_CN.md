# Qwen2 L0 cold→carried prefill 软件诊断（2026-10-11）

**结论：`DIAGNOSTIC_NOT_ACCEPTED`。** 实际 M16 与 M128 carried 均完成 Qwen2-1.5B 第 0 层完整 block 的 15 个主阶段及 29 个观察节点。M128 四种对照都有 15 个中间节点失败，虽然末输出 `y` 仍满足原 block 绝对误差门限。因此不能以末输出单门判定整个 block 或模型合格。

本批只完成 L0，两段各 M 个 token；没有执行全部 28 层、模型最终词表 logits、模型质量评测、RTL 或 EDA。没有改变规范、门限、原硬件或现有 runner 准入。旧 v0 的 `FAIL_EXISTING_FP32_FINAL_BUDGET` 连同原完整报告保留。

## 运行与输入边界

- 模型：`Qwen/Qwen2-1.5B-Instruct`，revision `ba1cf1846d7df0a0591d6c00649f57e798519da8`。
- 官方实现：固定 Transformers 4.40.1 / revision `9fe3f585` 对应的既有源码校验；Torch 2.10 CPU，线程上限 4。
- 固定载荷：`config/payload_pins/qwen2_layer0.json`；复用本地已验证的 12 个 BF16 权重/偏置张量及 embedding rows 0..255，没有下载新载荷。
- cold：复用封存的实际 candidate 输出，重新验证源、C++、ELF、原 raw、29 节点导出、只读 arena、原参考与数值报告。没有重跑 cold，**不声称同一个新 binary 连续执行的 cold/carried pair**。
- carried M16：新 embedding token IDs / 绝对位置 16..31，Q16 / K32；carried M128：IDs / 绝对位置 128..255，Q128 / K256。
- 每次 carried 的前缀 K 是上次实际 post-RoPE K，V 是上次实际投影 V；当前段所有中间值由本次实际上游阶段产生。官方中间值从未注入 candidate。
- dense 继续 BF16 乘数、按 K 递增的 FP32 FMA 与原 FP32 bias 顺序；QK 继续 16 stripe 归约；softmax/SiLU 保留原 exp7。继承版本化 BF16 materialization candidate，仍不符合 v0 硬件 RoPE 合约。
- 四种参考分列：官方自有 cold cache 链、独立 NumPy 自有 cold cache 链、官方计算以实际 candidate 前 cache 为条件、独立 NumPy 计算以实际 candidate 前 cache 为条件。

## 实际结果

M16 最终 carried C++ 用时 4.548964539 秒；M128 用时 30.658695787 秒。只报告软件墙钟时间，不推导硬件 cycle、利用率或性能。

| 规模 / 对照 | 失败节点 | y max_abs | y mean_abs |
|---|---|---:|---:|
| M16 官方自 cache | 无已定义门限失败 | 0.001953125 | 0.000009087535 |
| M16 官方条件 candidate cache | 无已定义门限失败 | 0.001953125 | 0.000009087535 |
| M16 独立自 cache | scores、logits | 0.0078125 | 0.000048576544 |
| M16 独立条件 candidate cache | scores、logits | 0.0078125 | 0.000038089153 |
| M128 官方自 cache | 下列全部 15 节点 | 0.0390625 | 0.000243411555 |
| M128 官方条件 candidate cache | 下列全部 15 节点 | 0.0390625 | 0.000242662500 |
| M128 独立自 cache | 下列全部 15 节点 | 0.0390625 | 0.000221450357 |
| M128 独立条件 candidate cache | 下列全部 15 节点 | 0.0390625 | 0.000220765602 |

M128 四种方法共同失败：`qr, q, scores, logits, prob, pv, att, o, r, n1, gate, up, silu, act, down`。M16 独立参考的 scores/logits max_abs 为 0.25，原失败保留。

每种方法检查 29 节点，其中 `softmax_fp32` 始终是 `DIAGNOSTIC_NO_APPROVED_FP32_TOLERANCE`，**没有将这个未定义的逐元素门写成通过**。另外独立检查其 FP32 行和误差 ≤2e-5。

M16、M128 的 14 项语义均通过：精确 causal mask、过去 cache 前缀不变、当前 K/V append 一致、未来概率为零、FP32 行和、BF16 probability materialization、GQA repeat、attention 布局、两个残差及 activation product。只读 arena 与未写尾区 deterministic NaN sentinel 也通过检查。这些语义通过不覆盖上述数值失败。

## 只读首差定位

本节统计直接读取封存数组，未重跑或修改整链。

1. `n0` 首次出现主链差异：35 个元素，全部在绝对 token 174 / 204，max_abs 0.0078125，仍在原 operator 门内。token 204 有 19 个不同元素。
2. 第一个超 operator 门限的主节点是 `qr`，它表示投影加 bias 后 materialize 的 BF16：token 204 / channel 443 为 -23.875 对 -23.75，max_abs 0.125。原始 pre-bias FP32 accumulator 未导出，不能从舍入后的 qr 倒推并声称它是实际 linear/bias 分离观测。
3. RoPE 另有独立表差异。cos 表有 12 个不同元素，max_abs 0.00048828125；sin 表有 10 个不同元素，max_abs 0.001953125。绝对位置 145 / frequency 3 的 sin 是 0.4609375 对官方 0.462890625，而 cos 相同。对应两个实际 qr 输入 21.875 / 12.1875 都与官方相同，q 却是 20.875 对 21.0。这里保留了既有 double-libm→FP32 table 与官方 FP32 table 的差异，不能把所有 Q 差异归给 RMS。
4. 最坏有效 logit：head 3 / 绝对 query 204 / key 26，为 -1936 对 -1920，误差 16。295680 个有效元素中 198 个不同、196 个超过 operator max_abs 0.03125；97536 个 masked logits 全一致。额外观察的 masked-future scores 中有 56 个不同，但它们未进入 attention。
5. head 2 / query 204 / key 200 的 BF16 概率是 0.2109375 对官方 0.03515625。该行 top-1 质量分别为 0.2109375 / 0.03515625，top-4 为 0.296630859375 / 0.140625。attention max_abs 为 0.171630859375。即使最终 y 过门，这个中间分布变化仍必须报告。
6. 官方自 cache 与官方条件 candidate cache 的 scores/logits/prob 逐位相同；attention 相互 max_abs 0.000244140625，y 相互 max_abs 0.00390625。这一条件对照没有消除本批失败。

## 额外单算子归因

在上述主链封存后，仅按授权执行了一次提取的原 C++ RMS helper、一次官方 eager RMS、两次官方 eager Q linear；全部固定原输入/权重/bias，未把结果替换进整链，也没有重跑 carried block。

| 检查 | max_abs | 不同元素 |
|---|---:|---:|
| 提取原 C++ norm 对封存实际 n0 | 0 | 0 |
| 明确 sequential FP32 RMS 方程对提取 C++ | 0 | 0 |
| 官方 RMS 对封存官方 n0 | 0 | 0 |
| 固定实际 n0：实际 qr 对官方 Q linear | 0.00390625 | 30 |
| 固定官方 n0：实际 qr 对官方 Q linear | 0.125 | 462 |
| 官方 n0 控制：新 Q linear 对封存官方 qr | 0 | 0 |

这表明该输入样例中，Q 的大部分差异已在 n0 输入差异传播后出现；同实际输入的 Q linear 残差明显更小。它没有证明 dense 与官方逐位等价，也不把门内 n0 差异直接认定为硬件缺陷。

当前 RMS：逐 channel `FP32 x*x`、顺序 FP32 add、乘 FP32 `1/1536`、加 epsilon、FP32 sqrt 后 reciprocal、归一化先 BF16 materialize、乘 gamma 后再 BF16 materialize。官方固定源码为 `pow(2).mean`、`torch.rsqrt`、FP32 归一化后转输入 dtype，再乘 gamma（`modeling_qwen2.py:85-90`）。现有 GDN helper 只接受 2 的幂宽且采用 `1+gamma`，不能不加修改地套到本例的 1536 / direct gamma。

token 204 的 sequential mean 为 0.0001884432858787477，官方 mean 为 0.00018844376609195024；inverse 分别为 72.65414428710938 / 72.654052734375。原 helper 与官方 helper 各自逐位复现原输出，支持上述运算顺序差异解释；没有引入新数值政策。

## 准入、测试及独立复核

- CLI 必须显式给 cold RESULT SHA；M128 还必须给已完成 M16 carried RESULT SHA。M16/M128 的 prior 长度、token、position、源、cache role、原始字节不可互换。
- launch 前固定生成器、C++、ELF、编译参数、payload pin、输入、cache binding、官方 runtime、原门限和 FROZEN SHA；完成后再核同一 SHA 与各项来源对应关系。
- 官方及独立参考的历史 cache 在实际消费时对**准确读入的字节**重验源 receipt hash。
- 56 个 focused tests 通过（carried、原 BF16 candidate、rectangular 三个套件）。覆盖旧/新 tiny past=0 所有输出 bit equivalence、前次实际 K 与 V 各自影响本次 att/y、当前 Q/K/V 不受该前 cache 改动、cache 破坏/伪造 hash/交换/alias/path traversal、position/source/receipt 拒绝、M16 准入 raw/reference/FROZEN 篡改等。
- 独立静态与证据复核：最终两个 RESULT、全部 listed artifacts、cold raw20 / export29、cache prefix/append 均吻合；每次运行 116 个 stage×method 行的 max_abs/mean_abs、张量 hash、门限结果及失败列表重算一致。该复核没有重新执行模型。

## 封存索引

完整紧凑清单（含命令、输入 SHA、四法 y 标量及 cache 来源）：`work/qwen2_carried_compact_manifest_20261011.json`，SHA256 `f8cbaf23934d5159f40e1a18bc32d5f68b6c3ee31fcb22b304024c86519883c7`。

| 证据 | SHA256 |
|---|---|
| 最终 M16 RESULT | `24b2c1b48549540cc8689701a270c6e80c1d79b9151a8c40676b7f2a1e773a52` |
| 最终 M16 FROZEN | `8e341f6cdb1d37f0368e458928f0e8bb795b11d6ed811b7d8c903e1f45fdf3ce` |
| 最终 M128 RESULT | `316b962a61bc53adc5b8d2a0885c977e1fffb52af05ed3667a6494f003eb59c6` |
| 最终 M128 FROZEN | `5ff8ac4c446ddc8e2e291a18b05d1978ee089979a50c51fe18c8edff25c67150` |
| 首轮 M16 RESULT，原样保留 | `e74ee6ccecd1dcd11fd8bf6b927da2a061fff85cca2ae1bf3f0ad1d67ca6af10` |
| 最终生成器 | `9df9ad51f98c7273ce8847a47a090093edd23c48289cf9e964f44a8ac3cd41b6` |
| 测试文件 | `937184c86d94bf9bde9c97227a6db6950dd5fc0290c31f01087694dfa66836aa` |
| carried C++，M16/M128 相同 | `0aaf9d3b96812694edb7adfd2fef5affb01ee206c8b743a64426752f59c60877` |
| carried ELF，M16/M128 相同 | `7b76e11af0f28ca9849fbd8984fcc580e108d03915e4bbcbdef128972cc22872` |
| 56 项测试回执 | `080e496982f334dde60b6f91b0b61d93b722a2df27775e21885aabe12f676786` |
| 只读首差统计 JSON | `df03842c4e5d052231e165d88e59b2f7eb93ebeb6d3d1a60c0733678dee39cc5` |
| 条件 Q / RMS 诊断脚本 | `b6e34ad2ca89ed5c6e35493933c18a8bf90d7d1de3ece2d108d2eeb82a5baee7` |
| 条件 Q / RMS RESULT | `3a65ed9599c24ef7ed002c3a2dae90c7c408818efd91cf4a41d1cbf266deb454` |
| 条件 Q / RMS FROZEN | `06d96bea21cfe499325c833d2a1e11ec6f494f2d3045ff3dc6c8ac5e9a889418` |

最终运行目录：`work/qwen2_carried_candidate_m16_final_20261011/`、`work/qwen2_carried_candidate_m128_final_20261011/`。首轮目录 `work/qwen2_carried_candidate_m16_20261011/` 不改写。单算子可复现入口为 `scripts/qwen2_carried_qlinear_rms_diagnostic.py`；报告实际执行时使用 `work/qwen2_carried_qlinear_rms_diagnostic.py`，两文件逐字相同、SHA 相同。原 work 源文件和结果目录 `work/qwen2_carried_qlinear_rms_20261011/` 均保留，没有为归档重跑。

M128 prior K / V 各 131072 字节，token-major 文件 SHA 分别为 `4235e281e15b19775085e0b4c2919ee2a433cc3e54f510b3ace76856d0b1fd60`、`d4858f057b4df5314b90825c1492d08b92d99e6880f8ab1421b70a76da6d79f5`，恰与原 cold raw k/v 匹配。cold RESULT SHA 为 `7b7de4815daf592b9a807f9057788b7aa815381f2e9c2e65e73ecf18b2c4bb29`。

所有权重、`.f32le` / BF16 数组、arena 与 ELF 仅留在 ignored `work/`，不进入 Git。可发布源为新增 carried driver、单算子诊断入口、测试、此文及经整理的紧凑 JSON 报告。所有 CLI 对已存在输出目录拒绝覆盖，诊断完成仍返回 exit 1 以避免被误用作硬件验收。

发布后的精确报告副本见 [封存目录](../reports/execution/QWEN2_CARRIED_MODEL_20261011/)，包括首轮、最终回执、独立复核、只读首差和单算子归因。`PRESERVATION.json` 对每个原样副本记录来源路径、字节数与 SHA256；本地原始数组继续保留。
